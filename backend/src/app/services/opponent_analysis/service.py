from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models import DocumentAsset, DocumentVectorStatus
from app.models.opponent_analysis import (
    OpponentAnalysisEvent,
    OpponentAnalysisEventType,
    OpponentAnalysisRun,
    OpponentAnalysisStatus,
)
from app.schemas.opponent_analysis import (
    OpponentAnalysisAgentPayload,
    OpponentAnalysisCitation,
    OpponentAnalysisDetailResponse,
    OpponentAnalysisEventItem,
    OpponentAnalysisListResponse,
    OpponentAnalysisOpponentPosition,
    OpponentAnalysisResponsePlan,
    OpponentAnalysisRunItem,
    OpponentAnalysisStreamSnapshot,
    OpponentAnalysisSummary,
)
from app.schemas.search import SearchResultItem


def build_empty_summary() -> OpponentAnalysisSummary:
    return OpponentAnalysisSummary(
        opponent_position=OpponentAnalysisOpponentPosition(),
        lawyer_predictions=OpponentAnalysisAgentPayload(),
        party_predictions=OpponentAnalysisAgentPayload(),
        response_plan=OpponentAnalysisResponsePlan(),
        evidence_index=[],
        risk_level="pending",
    )


class OpponentAnalysisService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def list_runs(self) -> OpponentAnalysisListResponse:
        rows = list(
            self.db.scalars(
                select(OpponentAnalysisRun).order_by(
                    OpponentAnalysisRun.updated_at.desc()
                )
            )
        )
        return OpponentAnalysisListResponse(
            items=[self._to_run_item(row) for row in rows]
        )

    def get_run(self, run_id: str) -> OpponentAnalysisDetailResponse:
        run = self._get_run_model(run_id, with_events=True)
        return OpponentAnalysisDetailResponse(
            run=self._to_run_item(run),
            events=[self._to_event_item(item) for item in run.events],
            summary=self._to_summary(run.summary_json),
        )

    def get_stream_snapshot(self, run_id: str) -> OpponentAnalysisStreamSnapshot:
        run = self._get_run_model(run_id, with_events=False)
        return OpponentAnalysisStreamSnapshot(
            run=self._to_run_item(run),
            summary=self._to_summary(run.summary_json),
            latest_seq=self.get_latest_seq(run_id),
        )

    def create_run(
        self,
        *,
        case_facts: str,
        top_k: int,
        document_ids: Sequence[str] | None,
    ) -> OpponentAnalysisDetailResponse:
        normalized_case_facts = case_facts.strip()
        if not normalized_case_facts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="case_facts must not be empty.",
            )

        selected_document_ids = self.validate_document_scope(document_ids or [])
        run = OpponentAnalysisRun(
            id=str(uuid4()),
            case_facts=normalized_case_facts,
            top_k=top_k,
            scope_document_ids_json=selected_document_ids,
            status=OpponentAnalysisStatus.queued.value,
            summary_json=build_empty_summary().model_dump(),
            risk_cards_json=[],
        )
        self.db.add(run)
        self.db.commit()

        self.append_event(
            run_id=run.id,
            phase="context_brief",
            round_number=0,
            from_agent=None,
            to_agent=None,
            event_type=OpponentAnalysisEventType.stage.value,
            title="预测任务已创建",
            content="后台多智能体推演已排队，稍后会持续写入过程事件。",
            structured_payload={
                "case_facts_preview": self._build_preview(normalized_case_facts),
                "document_scope_count": len(selected_document_ids),
            },
            citations=[],
            event_status=OpponentAnalysisStatus.queued.value,
        )

        from app.services.opponent_analysis.executor import submit_opponent_analysis_job

        submit_opponent_analysis_job(run.id)
        return self.get_run(run.id)

    def delete_run(self, run_id: str) -> None:
        run = self._get_run_model(run_id, with_events=False)
        self.db.delete(run)
        self.db.commit()

    def get_events_after(
        self, run_id: str, after_seq: int
    ) -> list[OpponentAnalysisEventItem]:
        self._get_run_model(run_id, with_events=False)
        events = list(
            self.db.scalars(
                select(OpponentAnalysisEvent)
                .where(
                    OpponentAnalysisEvent.run_id == run_id,
                    OpponentAnalysisEvent.seq > after_seq,
                )
                .order_by(OpponentAnalysisEvent.seq.asc())
            )
        )
        return [self._to_event_item(item) for item in events]

    def get_latest_seq(self, run_id: str) -> int:
        self._get_run_model(run_id, with_events=False)
        latest_seq = self.db.scalar(
            select(func.max(OpponentAnalysisEvent.seq)).where(
                OpponentAnalysisEvent.run_id == run_id
            )
        )
        return int(latest_seq or 0)

    def update_run_status(
        self,
        run_id: str,
        next_status: str,
        *,
        failure_reason: str | None = None,
    ) -> OpponentAnalysisRun:
        run = self._get_run_model(run_id, with_events=False)
        run.status = next_status
        run.failure_reason = failure_reason
        if next_status in {
            OpponentAnalysisStatus.completed.value,
            OpponentAnalysisStatus.failed.value,
        }:
            run.completed_at = func.now()
        self.db.commit()
        return run

    def complete_run(
        self,
        run_id: str,
        *,
        summary: OpponentAnalysisSummary,
        risk_cards: list[dict],
    ) -> OpponentAnalysisRun:
        run = self._get_run_model(run_id, with_events=False)
        run.status = OpponentAnalysisStatus.completed.value
        run.summary_json = summary.model_dump()
        run.risk_cards_json = risk_cards
        run.failure_reason = None
        run.completed_at = func.now()
        self.db.commit()
        return run

    def fail_run(self, run_id: str, failure_reason: str) -> OpponentAnalysisRun:
        run = self._get_run_model(run_id, with_events=False)
        run.status = OpponentAnalysisStatus.failed.value
        run.failure_reason = failure_reason
        run.completed_at = func.now()
        self.db.commit()
        return run

    def append_event(
        self,
        *,
        run_id: str,
        phase: str,
        round_number: int,
        from_agent: str | None,
        to_agent: str | None,
        event_type: str,
        title: str,
        content: str,
        structured_payload: dict,
        citations: list[dict],
        event_status: str,
    ) -> OpponentAnalysisEvent:
        self._get_run_model(run_id, with_events=False)
        event = OpponentAnalysisEvent(
            run_id=run_id,
            seq=self.get_latest_seq(run_id) + 1,
            phase=phase,
            round=round_number,
            from_agent=from_agent,
            to_agent=to_agent,
            event_type=event_type,
            title=title,
            content=content,
            structured_payload_json=structured_payload,
            citations_json=citations,
            status=event_status,
        )
        self.db.add(event)
        self.db.commit()
        return event

    def validate_document_scope(self, document_ids: Sequence[str]) -> list[str]:
        normalized = sorted({item for item in document_ids if item})
        if not normalized:
            return []

        rows = list(
            self.db.scalars(
                select(DocumentAsset).where(DocumentAsset.id.in_(normalized))
            )
        )
        row_map = {row.id: row for row in rows}
        missing_ids = [item for item in normalized if item not in row_map]
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown document ids: {', '.join(missing_ids)}",
            )

        not_indexed_ids = [
            row.id
            for row in rows
            if row.vector_status != DocumentVectorStatus.indexed.value
        ]
        if not_indexed_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "All scoped documents must be indexed before opponent analysis. "
                    f"Not indexed: {', '.join(sorted(not_indexed_ids))}"
                ),
            )
        return normalized

    def build_citations_from_sources(
        self,
        sources: Sequence[SearchResultItem],
        *,
        limit: int | None = None,
    ) -> list[dict]:
        citations: list[dict] = []
        for index, item in enumerate(sources, start=1):
            citations.append(
                OpponentAnalysisCitation(
                    citation_number=index,
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    original_filename=item.original_filename,
                    page_number=item.page_number,
                    snippet=self._clip_text(
                        item.content,
                        self.settings.answer_generation_max_content_chars,
                    ),
                    score=item.score,
                    metadata=item.metadata,
                ).model_dump()
            )
            if limit is not None and len(citations) >= limit:
                break
        return citations

    def build_citations_by_number(
        self,
        evidence_cards: Sequence[dict],
        citation_numbers: Sequence[int],
    ) -> list[dict]:
        cards_by_number = {
            int(card.get("citation_number", 0)): card
            for card in evidence_cards
            if int(card.get("citation_number", 0)) > 0
        }
        citations: list[dict] = []
        for item in citation_numbers:
            try:
                number = int(item)
            except (TypeError, ValueError):
                continue
            card = cards_by_number.get(number)
            if card:
                citations.append(card)
        return citations

    def _get_run_model(self, run_id: str, *, with_events: bool) -> OpponentAnalysisRun:
        statement = select(OpponentAnalysisRun).where(OpponentAnalysisRun.id == run_id)
        if with_events:
            statement = statement.options(selectinload(OpponentAnalysisRun.events))
        run = self.db.scalar(statement)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Opponent analysis run not found.",
            )
        return run

    def _to_run_item(self, run: OpponentAnalysisRun) -> OpponentAnalysisRunItem:
        summary = self._to_summary(run.summary_json)
        return OpponentAnalysisRunItem(
            id=run.id,
            case_facts=run.case_facts,
            case_facts_preview=self._build_preview(run.case_facts),
            top_k=run.top_k,
            scope_document_ids=list(run.scope_document_ids_json or []),
            status=run.status,
            risk_level=summary.risk_level
            if run.status == OpponentAnalysisStatus.completed.value
            else None,
            failure_reason=run.failure_reason,
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
        )

    def _to_event_item(self, event: OpponentAnalysisEvent) -> OpponentAnalysisEventItem:
        return OpponentAnalysisEventItem(
            id=event.id,
            seq=event.seq,
            phase=event.phase,
            round=event.round,
            from_agent=event.from_agent,
            to_agent=event.to_agent,
            event_type=event.event_type,
            title=event.title,
            content=event.content,
            structured_payload=dict(event.structured_payload_json or {}),
            citations=[
                OpponentAnalysisCitation.model_validate(item)
                for item in (event.citations_json or [])
            ],
            status=event.status,
            created_at=event.created_at,
        )

    def _to_summary(self, payload: dict | None) -> OpponentAnalysisSummary:
        if not payload:
            return build_empty_summary()
        try:
            return OpponentAnalysisSummary.model_validate(payload)
        except Exception:
            return build_empty_summary()

    @staticmethod
    def _build_preview(value: str, limit: int = 88) -> str:
        normalized = " ".join((value or "").split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

    @staticmethod
    def _clip_text(value: str, limit: int) -> str:
        normalized = " ".join((value or "").split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."
