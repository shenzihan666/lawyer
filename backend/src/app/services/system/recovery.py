from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    ContractReviewJob,
    ContractReviewJobStatus,
    OpponentAnalysisRun,
    OpponentAnalysisStatus,
)
from app.services.analytics import AnalyticsService
from app.services.opponent_analysis.service import OpponentAnalysisService

logger = logging.getLogger("app.system.recovery")


class StartupRecoveryService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.analytics = AnalyticsService(db=db, settings=settings)

    def reconcile(self) -> dict[str, int]:
        run = self.analytics.start_run(run_kind="startup_recovery")
        summary = {
            "opponent_runs_requeued": 0,
            "opponent_runs_failed": 0,
            "contract_jobs_requeued": 0,
            "contract_jobs_failed": 0,
        }
        try:
            summary["opponent_runs_requeued"] = self._requeue_queued_opponent_runs()
            summary["opponent_runs_failed"] = self._fail_stale_opponent_runs()
            summary["contract_jobs_requeued"] = self._requeue_queued_contract_jobs()
            summary["contract_jobs_failed"] = self._fail_stale_contract_jobs()

            self.analytics.append_step(
                run.id,
                step_key="reconcile",
                title="Startup recovery reconciled persisted jobs",
                status="done",
                payload=summary,
            )
            self.analytics.finish_run(run.id, status="completed", summary=summary)
            return summary
        except Exception as exc:
            self.analytics.append_step(
                run.id,
                step_key="reconcile",
                title="Startup recovery failed",
                status="error",
                payload={"error": str(exc)},
            )
            self.analytics.finish_run(
                run.id,
                status="failed",
                summary={"error": str(exc), **summary},
            )
            raise

    def _requeue_queued_opponent_runs(self) -> int:
        from app.services.opponent_analysis.executor import submit_opponent_analysis_job

        queued_runs = list(
            self.db.scalars(
                select(OpponentAnalysisRun).where(
                    OpponentAnalysisRun.status == OpponentAnalysisStatus.queued.value
                )
            )
        )
        if not queued_runs:
            return 0

        service = OpponentAnalysisService(db=self.db, settings=self.settings)
        for run in queued_runs:
            service.append_event(
                run_id=run.id,
                phase="context_brief",
                round_number=0,
                from_agent=None,
                to_agent=None,
                event_type="stage",
                title="系统恢复后重新排队",
                content="服务重启后发现任务仍处于排队状态，已重新提交后台执行。",
                structured_payload={"recovered_by": "startup_recovery"},
                citations=[],
                event_status=OpponentAnalysisStatus.queued.value,
            )
            submit_opponent_analysis_job(run.id)
        logger.info(
            "Requeued opponent analysis runs on startup",
            extra={
                "event": "startup_recovery_opponent_requeued",
                "count": len(queued_runs),
            },
        )
        return len(queued_runs)

    def _fail_stale_opponent_runs(self) -> int:
        running_runs = list(
            self.db.scalars(
                select(OpponentAnalysisRun).where(
                    OpponentAnalysisRun.status == OpponentAnalysisStatus.running.value
                )
            )
        )
        if not running_runs:
            return 0

        service = OpponentAnalysisService(db=self.db, settings=self.settings)
        for run in running_runs:
            service.append_event(
                run_id=run.id,
                phase="finalize",
                round_number=0,
                from_agent=None,
                to_agent=None,
                event_type="error",
                title="系统恢复时发现中断任务",
                content="该任务在上次进程退出时未完成，已标记失败，请重新发起以避免重复事件。",
                structured_payload={"recovered_by": "startup_recovery"},
                citations=[],
                event_status="error",
            )
            service.fail_run(
                run.id,
                "Recovered from unexpected shutdown while opponent analysis was running.",
            )
        return len(running_runs)

    def _requeue_queued_contract_jobs(self) -> int:
        from app.services.contract_review.executor import submit_review_job

        queued_jobs = list(
            self.db.scalars(
                select(ContractReviewJob).where(
                    ContractReviewJob.status == ContractReviewJobStatus.queued.value
                )
            )
        )
        for job in queued_jobs:
            submit_review_job(job.id)
        return len(queued_jobs)

    def _fail_stale_contract_jobs(self) -> int:
        running_jobs = list(
            self.db.scalars(
                select(ContractReviewJob).where(
                    ContractReviewJob.status == ContractReviewJobStatus.running.value
                )
            )
        )
        for job in running_jobs:
            job.status = ContractReviewJobStatus.failed.value
            job.failure_reason = (
                "Recovered from unexpected shutdown while contract review was running."
            )
        if running_jobs:
            self.db.commit()
        return len(running_jobs)
