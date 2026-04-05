from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.conversation import ConversationMeta
from app.schemas.conversation import AgentChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


def _translate_event(event: dict) -> dict | None:
    """Translate a LangGraph astream_events event to our SSE format.

    Returns None for events we don't want to forward to the client.
    """
    kind = event.get("event")

    # Token-by-token streaming from the chat model
    if kind == "on_chat_model_stream":
        chunk = event.get("data", {}).get("chunk")
        if not chunk:
            return None
        content = ""
        # Handle different chunk formats
        if hasattr(chunk, "content"):
            c = chunk.content
            if isinstance(c, str):
                content = c
            elif isinstance(c, list):
                content = "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in c
                )
        if content:
            return {"type": "content", "content": content}
        return None

    # Tool execution starts → emit rag_step
    if kind == "on_tool_start":
        tool_name = event.get("name", "")
        if tool_name == "legal_knowledge_search":
            tool_input = event.get("data", {}).get("input", {})
            query_preview = str(tool_input.get("query", ""))[:50]
            return {
                "type": "rag_step",
                "step": {
                    "key": "rag-search",
                    "label": "正在检索法律知识库",
                    "detail": query_preview,
                    "status": "running",
                },
            }
        return None

    # Tool execution ends → emit result with citations
    if kind == "on_tool_end":
        tool_name = event.get("name", "")
        if tool_name == "legal_knowledge_search":
            output = event.get("data", {}).get("output")
            if isinstance(output, dict):
                return {
                    "type": "result",
                    **output,
                }
            return {
                "type": "rag_step",
                "step": {
                    "key": "rag-search-done",
                    "label": "检索完成",
                    "detail": "",
                    "status": "done",
                },
            }
        return None

    return None


async def _generate_title(query: str) -> str:
    """Generate a short conversation title from the first user message."""
    import httpx

    settings = get_settings()
    if not (
        settings.answer_generation_base_url
        and settings.answer_generation_model
        and settings.answer_generation_api_key
    ):
        return query[:20] + ("..." if len(query) > 20 else "")

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{settings.answer_generation_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.answer_generation_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.answer_generation_model,
                    "temperature": 0,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "请为以下对话生成一个简短的标题（不超过15个字），"
                                "只输出标题本身，不要加引号或其他格式：\n\n"
                                f"{query[:200]}"
                            ),
                        }
                    ],
                },
            )
            data = resp.json()
            title = data["choices"][0]["message"]["content"].strip().strip('"\'')
            return title[:50]
    except Exception as exc:
        logger.warning("Title generation failed: %s", exc)
        return query[:20] + ("..." if len(query) > 20 else "")


@router.post("/stream")
async def agent_chat_stream(
    request: AgentChatRequest,
    db: Session = Depends(get_db),
):
    """Stream agent responses via SSE, with conversation persistence."""
    from app.services.agent.checkpoint import get_checkpointer
    from app.services.agent.factory import create_lawyer_agent

    settings = get_settings()
    if not settings.agent_enabled:
        return StreamingResponse(
            iter(["data: " + json.dumps({"type": "error", "content": "Agent is disabled"}) + "\n\n"]),
            media_type="text/event-stream",
        )

    checkpointer = await get_checkpointer()
    agent = create_lawyer_agent(checkpointer)

    is_new = not request.thread_id
    thread_id = request.thread_id or str(uuid4())

    # Create conversation meta for new conversations
    if is_new:
        meta = ConversationMeta(
            thread_id=thread_id,
            title=await _generate_title(request.query),
            last_message_preview=request.query[:200],
        )
        db.add(meta)
        db.commit()

    async def event_generator():
        import traceback as tb_module

        try:
            config = {"configurable": {"thread_id": thread_id}}

            input_messages = {"messages": [{"role": "user", "content": request.query}]}

            logger.info(
                "Starting agent stream",
                extra={
                    "event": "agent_stream_start",
                    "thread_id": thread_id,
                    "query_length": len(request.query),
                },
            )

            async for event in agent.astream_events(
                input_messages,
                config=config,
                version="v2",
            ):
                translated = _translate_event(event)
                if translated:
                    yield f"data: {json.dumps(translated, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"

            # Update conversation meta after successful response
            _update_conversation_meta(db, thread_id, request.query)

        except Exception as exc:
            full_tb = tb_module.format_exc()
            error_msg = str(exc) or repr(exc) or type(exc).__name__
            logger.error(
                "Agent stream error",
                extra={
                    "event": "agent_stream_error",
                    "error": error_msg,
                    "error_type": type(exc).__name__,
                    "traceback": full_tb,
                },
            )
            error_event = {"type": "error", "content": f"{error_msg}"}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    response = StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "x-thread-id": thread_id,
        },
    )
    return response


def _update_conversation_meta(
    db: Session,
    thread_id: str,
    query: str,
):
    """Update conversation metadata after a successful exchange."""
    try:
        meta = db.query(ConversationMeta).filter_by(thread_id=thread_id).first()
        if meta:
            meta.message_count += 2  # user + assistant
            meta.last_message_preview = query[:200]
            db.commit()
    except Exception as exc:
        logger.warning("Failed to update conversation meta: %s", exc)
