from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    SystemAnalyticsEvent,
    SystemTrajectoryRun,
    SystemTrajectoryStatus,
    SystemTrajectoryStep,
)

logger = logging.getLogger("app.analytics")


class AnalyticsService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def record_event(
        self,
        *,
        category: str,
        event_name: str,
        status: str = "info",
        trace_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        payload: dict | None = None,
    ) -> SystemAnalyticsEvent:
        event = SystemAnalyticsEvent(
            category=category,
            event_name=event_name,
            status=status,
            trace_id=trace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            payload_json=dict(payload or {}),
        )
        self.db.add(event)
        self.db.commit()
        logger.info(
            "Analytics event recorded",
            extra={
                "event": "analytics_event_recorded",
                "analytics_category": category,
                "analytics_name": event_name,
                "analytics_status": status,
                "trace_id": trace_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "payload": payload or {},
            },
        )
        return event

    def start_run(
        self,
        *,
        run_kind: str,
        trace_id: str | None = None,
        parent_run_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> SystemTrajectoryRun:
        run = SystemTrajectoryRun(
            id=str(uuid4()),
            run_kind=run_kind,
            status=SystemTrajectoryStatus.running.value,
            trace_id=trace_id,
            parent_run_id=parent_run_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=dict(metadata or {}),
            summary_json={},
        )
        self.db.add(run)
        self.db.commit()
        return run

    def append_step(
        self,
        run_id: str,
        *,
        step_key: str,
        title: str,
        status: str = "running",
        payload: dict | None = None,
    ) -> SystemTrajectoryStep:
        next_seq = (
            int(
                self.db.scalar(
                    select(func.max(SystemTrajectoryStep.seq)).where(
                        SystemTrajectoryStep.run_id == run_id
                    )
                )
                or 0
            )
            + 1
        )
        step = SystemTrajectoryStep(
            run_id=run_id,
            seq=next_seq,
            step_key=step_key,
            title=title,
            status=status,
            payload_json=dict(payload or {}),
        )
        self.db.add(step)
        self.db.commit()
        return step

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        summary: dict | None = None,
    ) -> SystemTrajectoryRun:
        run = self.db.scalar(
            select(SystemTrajectoryRun).where(SystemTrajectoryRun.id == run_id)
        )
        if run is None:
            raise RuntimeError(f"Trajectory run not found: {run_id}")

        run.status = status
        run.summary_json = dict(summary or {})
        if status in {
            SystemTrajectoryStatus.completed.value,
            SystemTrajectoryStatus.failed.value,
        }:
            run.completed_at = func.now()
        self.db.commit()
        return run
