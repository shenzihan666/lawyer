from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import get_settings
from app.services.agent.tools import legal_knowledge_search

logger = logging.getLogger(__name__)

LEGAL_SYSTEM_PROMPT = """\
You are a legal knowledge base assistant.

You must answer strictly based on the retrieved sources and never invent laws,
case numbers, facts, or conclusions.

When you need evidence from the knowledge base, use the
`legal_knowledge_search` tool. The tool performs retrieval, reranking, and
returns a grounded answer with citations.

Core rules:
1. Only cite source numbers returned by the knowledge base.
2. Answer directly first, then explain the supporting basis.
3. If the available information is insufficient, say so explicitly.
4. You may call the retrieval tool multiple times when needed.
5. Stay professional and cautious.
6. Always answer in Chinese.
7. If the current request already limits document scope or source count, you
   must respect those constraints and never broaden them on your own.
"""


def _build_legal_search_tool(
    default_top_k: int = 5,
    default_document_ids: list[str] | None = None,
):
    """Create a request-scoped search tool so UI retrieval settings always apply."""

    scoped_top_k = max(1, min(int(default_top_k), 10))
    scoped_document_ids = [doc_id for doc_id in (default_document_ids or []) if doc_id]

    @tool("legal_knowledge_search")
    def request_scoped_legal_knowledge_search(
        query: str,
        top_k: int | None = None,
        document_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search the legal knowledge base with request-scoped retrieval defaults."""

        effective_top_k = scoped_top_k
        effective_document_ids = (
            scoped_document_ids if scoped_document_ids else (document_ids or [])
        )
        return legal_knowledge_search.invoke(
            {
                "query": query,
                "top_k": effective_top_k,
                "document_ids": effective_document_ids,
            }
        )

    return request_scoped_legal_knowledge_search


def create_lawyer_agent(
    checkpointer: AsyncPostgresSaver,
    default_top_k: int = 5,
    default_document_ids: list[str] | None = None,
):
    """Create and return a compiled Deep Agent for legal Q&A."""
    from deepagents import create_deep_agent

    settings = get_settings()
    legal_search_tool = _build_legal_search_tool(
        default_top_k=default_top_k,
        default_document_ids=default_document_ids,
    )

    model = ChatOpenAI(
        model=settings.answer_generation_model or "gpt-4o",
        base_url=settings.answer_generation_base_url,
        api_key=settings.answer_generation_api_key or "sk-placeholder",
        temperature=0,
        streaming=True,
    )

    try:
        agent = create_deep_agent(
            model=model,
            tools=[legal_search_tool],
            system_prompt=LEGAL_SYSTEM_PROMPT,
            checkpointer=checkpointer,
        )
    except TypeError as exc:
        logger.warning(
            "create_deep_agent() rejected kwargs, falling back: %s",
            exc,
        )
        agent = create_deep_agent(
            model=model,
            tools=[legal_search_tool],
            system_prompt=LEGAL_SYSTEM_PROMPT,
        )

    logger.info(
        "Lawyer agent created",
        extra={
            "event": "agent_created",
            "model": settings.answer_generation_model,
            "default_top_k": default_top_k,
            "default_document_ids_count": len(default_document_ids or []),
        },
    )
    return agent
