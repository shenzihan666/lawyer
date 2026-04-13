from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.analytics import AnalyticsService


@dataclass(slots=True)
class GovernedToolPayload:
    query: str
    top_k: int
    document_ids: list[str]


class ToolGovernanceService:
    """Central policy gate for tool execution.

    The model only sees tools that call into this service, so policy checks
    and audit writes happen in host code rather than in the prompt.
    """

    allowed_tools = {"legal_knowledge_search"}
    max_document_ids = 50
    max_query_chars = 4000
    max_top_k = 10

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.analytics = AnalyticsService(db=db, settings=settings)

    def execute_legal_knowledge_search(
        self,
        *,
        query: str,
        top_k: int,
        document_ids: list[str] | None,
        executor: Callable[[GovernedToolPayload], dict[str, Any]],
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        run = self.analytics.start_run(
            run_kind="tool_governance",
            trace_id=trace_id,
            resource_type="tool",
            resource_id="legal_knowledge_search",
            metadata={
                "requested_top_k": top_k,
                "requested_document_ids": document_ids or [],
            },
        )
        try:
            payload = self._authorize_legal_knowledge_search(
                query=query,
                top_k=top_k,
                document_ids=document_ids,
                trace_id=trace_id,
                run_id=run.id,
            )
            self.analytics.append_step(
                run.id,
                step_key="dispatch",
                title="Tool request passed governance policy",
                status="done",
                payload={
                    "tool_name": "legal_knowledge_search",
                    "effective_top_k": payload.top_k,
                    "effective_document_count": len(payload.document_ids),
                },
            )
            result = executor(payload)
            self.analytics.record_event(
                category="tool",
                event_name="tool_execution_completed",
                status="success",
                trace_id=trace_id,
                resource_type="tool",
                resource_id="legal_knowledge_search",
                payload={
                    "effective_top_k": payload.top_k,
                    "effective_document_count": len(payload.document_ids),
                },
            )
            self.analytics.finish_run(
                run.id,
                status="completed",
                summary={
                    "tool_name": "legal_knowledge_search",
                    "effective_top_k": payload.top_k,
                    "effective_document_count": len(payload.document_ids),
                },
            )
            return result
        except Exception as exc:
            self.analytics.record_event(
                category="tool",
                event_name="tool_execution_blocked",
                status="error",
                trace_id=trace_id,
                resource_type="tool",
                resource_id="legal_knowledge_search",
                payload={"error": str(exc)},
            )
            self.analytics.finish_run(
                run.id,
                status="failed",
                summary={"error": str(exc)},
            )
            raise

    def _authorize_legal_knowledge_search(
        self,
        *,
        query: str,
        top_k: int,
        document_ids: list[str] | None,
        trace_id: str | None,
        run_id: str,
    ) -> GovernedToolPayload:
        if "legal_knowledge_search" not in self.allowed_tools:
            raise RuntimeError("Tool is not allowed by governance policy.")

        normalized_query = " ".join((query or "").split())[
            : self.max_query_chars
        ].strip()
        if not normalized_query:
            raise ValueError("Tool query must not be empty.")

        normalized_top_k = max(1, min(int(top_k or 1), self.max_top_k))
        normalized_document_ids = [
            str(item).strip() for item in (document_ids or []) if str(item).strip()
        ][: self.max_document_ids]

        self.analytics.append_step(
            run_id,
            step_key="policy_check",
            title="Tool request evaluated against allowlist policy",
            status="done",
            payload={
                "trace_id": trace_id,
                "tool_name": "legal_knowledge_search",
                "query_length": len(normalized_query),
                "requested_top_k": top_k,
                "effective_top_k": normalized_top_k,
                "effective_document_count": len(normalized_document_ids),
            },
        )
        return GovernedToolPayload(
            query=normalized_query,
            top_k=normalized_top_k,
            document_ids=normalized_document_ids,
        )
