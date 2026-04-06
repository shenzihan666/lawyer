from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.conversation import ConversationMeta
from app.schemas.conversation import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageItem,
    MessageListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _normalize_message_role(role: object, msg: object) -> str:
    normalized = str(role or "").strip().lower()
    if normalized in {"user", "assistant", "system", "tool"}:
        return normalized
    if normalized == "human":
        return "user"
    if normalized == "ai":
        return "assistant"

    msg_type = str(getattr(msg, "type", "") or "").strip().lower()
    if msg_type == "human":
        return "user"
    if msg_type == "ai":
        return "assistant"
    if msg_type in {"system", "tool"}:
        return msg_type

    return normalized or "unknown"


def _meta_to_response(meta: ConversationMeta) -> ConversationResponse:
    return ConversationResponse(
        thread_id=meta.thread_id,
        title=meta.title,
        message_count=meta.message_count,
        last_message_preview=meta.last_message_preview,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
    )


def _stringify_message_content(content: object) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        return " ".join(
            str(item) if isinstance(item, str) else str(item.get("text", ""))
            for item in content
            if isinstance(item, (str, dict))
        )

    if content is None:
        return ""

    return str(content)


def _parse_tool_result_content(content: object) -> dict | None:
    if isinstance(content, dict):
        return content

    if isinstance(content, str):
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    return None


@router.get("", response_model=ConversationListResponse)
def list_conversations(db: Session = Depends(get_db)):
    rows = db.query(ConversationMeta).order_by(ConversationMeta.updated_at.desc()).all()
    return ConversationListResponse(items=[_meta_to_response(r) for r in rows])


@router.post(
    "", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED
)
def create_conversation(
    body: ConversationCreate | None = None,
    db: Session = Depends(get_db),
):
    thread_id = str(uuid4())
    meta = ConversationMeta(
        thread_id=thread_id,
        title=(body.title if body and body.title else "新对话"),
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return _meta_to_response(meta)


@router.get("/{thread_id}", response_model=ConversationResponse)
def get_conversation(thread_id: str, db: Session = Depends(get_db)):
    meta = db.query(ConversationMeta).filter_by(thread_id=thread_id).first()
    if not meta:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _meta_to_response(meta)


@router.patch("/{thread_id}", response_model=ConversationResponse)
def update_conversation(
    thread_id: str,
    body: ConversationUpdate,
    db: Session = Depends(get_db),
):
    meta = db.query(ConversationMeta).filter_by(thread_id=thread_id).first()
    if not meta:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if body.title is not None:
        meta.title = body.title
    db.commit()
    db.refresh(meta)
    return _meta_to_response(meta)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(thread_id: str, db: Session = Depends(get_db)):
    meta = db.query(ConversationMeta).filter_by(thread_id=thread_id).first()
    if not meta:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(meta)
    db.commit()


@router.get("/{thread_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(thread_id: str):
    """Get message history for a conversation from the LangGraph checkpointer."""
    from app.services.agent.checkpoint import get_checkpointer

    checkpointer = await get_checkpointer()

    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = await checkpointer.aget(config)
    except Exception:
        state = None

    if not state:
        return MessageListResponse(thread_id=thread_id, messages=[])

    messages_raw = state.get("channel_values", {}).get("messages", [])
    messages: list[MessageItem] = []
    for msg in messages_raw:
        if isinstance(msg, dict):
            role = _normalize_message_role(msg.get("role"), msg)
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            name = msg.get("name")
        else:
            role = _normalize_message_role(getattr(msg, "role", None), msg)
            content = getattr(msg, "content", "")
            tool_calls = getattr(msg, "tool_calls", None)
            name = getattr(msg, "name", None)

        # Skip system messages from the UI
        if role == "system":
            continue

        # Skip assistant messages that only initiate tool calls.
        if tool_calls:
            continue

        citations = []
        meta = {}
        if role == "tool" or name:
            data = _parse_tool_result_content(content)
            if isinstance(data, dict) and "answer" in data:
                role = "assistant"
                content = data["answer"]
                citations = data.get("citations", [])
                meta = data.get("meta", {})

        content = _stringify_message_content(content)

        messages.append(
            MessageItem(
                role=role,
                content=str(content),
                citations=citations,
                meta=meta,
            )
        )

    return MessageListResponse(thread_id=thread_id, messages=messages)
