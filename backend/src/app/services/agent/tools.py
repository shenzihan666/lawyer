from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import tool

from app.core.config import get_settings
from app.core.logging import request_id_context
from app.db.session import get_session_factory
from app.services.governance import ToolGovernanceService

logger = logging.getLogger(__name__)


@tool
def legal_knowledge_search(
    query: str,
    top_k: int = 5,
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Search the legal knowledge base and generate a grounded answer with citations.

    Use this tool when the user asks a legal question that requires evidence
    from the knowledge base. Returns a structured answer with citations and
    source references.

    Args:
        query: The legal question to search for.
        top_k: Number of source documents to retrieve (default 5).
        document_ids: Optional list of specific document IDs to search within.
    """
    from app.services.answers.service import DocumentAnswerService

    settings = get_settings()
    session_factory = get_session_factory()
    db = session_factory()
    try:
        governance = ToolGovernanceService(db=db, settings=settings)
        trace_id = request_id_context.get()
        result = governance.execute_legal_knowledge_search(
            query=query,
            top_k=top_k,
            document_ids=document_ids,
            trace_id=trace_id,
            executor=lambda payload: (
                DocumentAnswerService(db=db, settings=settings)
                .answer(
                    query=payload.query,
                    top_k=payload.top_k,
                    document_ids=payload.document_ids,
                )
                .model_dump()
            ),
        )
        return result
    except Exception as exc:
        logger.warning(
            "legal_knowledge_search tool failed",
            extra={"event": "tool_error", "query": query, "error": str(exc)},
        )
        return {
            "answer": f"检索失败：{exc}",
            "citations": [],
            "meta": {"generation_mode": "error", "error": str(exc)},
        }
    finally:
        db.close()


async def legal_knowledge_search_async(
    query: str,
    top_k: int = 5,
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Async wrapper for legal_knowledge_search to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: legal_knowledge_search.invoke(
            {
                "query": query,
                "top_k": top_k,
                "document_ids": document_ids,
            }
        ),
    )
