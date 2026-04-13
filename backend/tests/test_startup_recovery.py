from uuid import uuid4

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import (
    ContractReviewJob,
    ContractReviewJobStatus,
    ContractReviewTemplate,
    OpponentAnalysisRun,
    OpponentAnalysisStatus,
)
from app.services.system import StartupRecoveryService


def test_startup_recovery_requeues_queued_jobs_and_fails_running_jobs(
    client,
    monkeypatch,
) -> None:
    opponent_requeued: list[str] = []
    review_requeued: list[str] = []

    monkeypatch.setattr(
        "app.services.opponent_analysis.executor.submit_opponent_analysis_job",
        lambda run_id: opponent_requeued.append(run_id),
    )
    monkeypatch.setattr(
        "app.services.contract_review.executor.submit_review_job",
        lambda job_id: review_requeued.append(job_id),
    )

    session = get_session_factory()()
    try:
        template = ContractReviewTemplate(
            id=str(uuid4()),
            name="模板",
            original_filename="template.xlsx",
            stored_filename="template.xlsx",
            storage_path="tests/template.xlsx",
            file_extension=".xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            sha256="template-sha",
            file_size=128,
            config_json={},
            metadata_json={},
        )
        session.add(template)

        queued_run = OpponentAnalysisRun(
            id=str(uuid4()),
            case_facts="queued facts",
            top_k=3,
            scope_document_ids_json=[],
            status=OpponentAnalysisStatus.queued.value,
            summary_json={},
            risk_cards_json=[],
        )
        running_run = OpponentAnalysisRun(
            id=str(uuid4()),
            case_facts="running facts",
            top_k=3,
            scope_document_ids_json=[],
            status=OpponentAnalysisStatus.running.value,
            summary_json={},
            risk_cards_json=[],
        )
        queued_job = ContractReviewJob(
            id=str(uuid4()),
            template_id=template.id,
            review_name="queued review",
            status=ContractReviewJobStatus.queued.value,
            original_filename="contract.docx",
            stored_filename="contract.docx",
            storage_path="tests/contract.docx",
            file_extension=".docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            sha256="queued-job-sha",
            file_size=128,
            summary_json={},
            result_snapshot_json={},
            metadata_json={},
        )
        running_job = ContractReviewJob(
            id=str(uuid4()),
            template_id=template.id,
            review_name="running review",
            status=ContractReviewJobStatus.running.value,
            original_filename="contract.docx",
            stored_filename="contract.docx",
            storage_path="tests/contract.docx",
            file_extension=".docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            sha256="running-job-sha",
            file_size=128,
            summary_json={},
            result_snapshot_json={},
            metadata_json={},
        )
        session.add_all([queued_run, running_run, queued_job, running_job])
        session.commit()

        summary = StartupRecoveryService(session, get_settings()).reconcile()
        session.expire_all()

        refreshed_running_run = session.scalar(
            select(OpponentAnalysisRun).where(OpponentAnalysisRun.id == running_run.id)
        )
        refreshed_running_job = session.scalar(
            select(ContractReviewJob).where(ContractReviewJob.id == running_job.id)
        )

        assert summary == {
            "opponent_runs_requeued": 1,
            "opponent_runs_failed": 1,
            "contract_jobs_requeued": 1,
            "contract_jobs_failed": 1,
        }
        assert opponent_requeued == [queued_run.id]
        assert review_requeued == [queued_job.id]
        assert refreshed_running_run is not None
        assert refreshed_running_run.status == OpponentAnalysisStatus.failed.value
        assert refreshed_running_job is not None
        assert refreshed_running_job.status == ContractReviewJobStatus.failed.value
    finally:
        session.close()
