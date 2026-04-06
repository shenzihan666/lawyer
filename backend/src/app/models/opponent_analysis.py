from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OpponentAnalysisStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class OpponentAnalysisEventType(str, enum.Enum):
    stage = "stage"
    agent_message = "agent_message"
    agent_revision = "agent_revision"
    evidence = "evidence"
    summary = "summary"
    error = "error"


class OpponentAnalysisRun(Base):
    __tablename__ = "opponent_analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_facts: Mapped[str] = mapped_column(Text)
    top_k: Mapped[int] = mapped_column(Integer, default=5)
    scope_document_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(
        String(32),
        default=OpponentAnalysisStatus.queued.value,
        index=True,
    )
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    risk_cards_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    events: Mapped[list["OpponentAnalysisEvent"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="OpponentAnalysisEvent.seq",
    )


class OpponentAnalysisEvent(Base):
    __tablename__ = "opponent_analysis_events"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_opponent_analysis_events_run_seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("opponent_analysis_runs.id", ondelete="CASCADE"),
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(64), index=True)
    round: Mapped[int] = mapped_column(Integer, default=0)
    from_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_agent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(
        String(32), default=OpponentAnalysisEventType.stage.value
    )
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    structured_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    citations_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="done")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    run: Mapped[OpponentAnalysisRun] = relationship(back_populates="events")
