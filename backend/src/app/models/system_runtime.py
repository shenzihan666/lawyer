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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SystemTrajectoryStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


class SystemAnalyticsEvent(Base):
    __tablename__ = "system_analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    event_name: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="info", index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resource_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class SystemTrajectoryRun(Base):
    __tablename__ = "system_trajectory_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default=SystemTrajectoryStatus.running.value,
        index=True,
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    parent_run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    resource_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(
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

    steps: Mapped[list["SystemTrajectoryStep"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="SystemTrajectoryStep.seq",
    )


class SystemTrajectoryStep(Base):
    __tablename__ = "system_trajectory_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_system_trajectory_steps_run_seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("system_trajectory_runs.id", ondelete="CASCADE"),
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer)
    step_key: Mapped[str] = mapped_column(String(96), index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    run: Mapped[SystemTrajectoryRun] = relationship(back_populates="steps")
