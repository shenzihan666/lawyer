from datetime import datetime, timezone
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.models import (
    ContractReviewClause,
    ContractReviewFinding,
    ContractReviewJob,
    ContractReviewJobStatus,
)
from app.services.contract_review.analysis import analyze_contract
from app.services.contract_review.clause_parser import parse_clauses
from app.services.contract_review.report import build_review_report
from app.services.contract_review.review_analyzer import ContractReviewLLMAnalyzer
from app.services.contract_review.storage import ContractReviewStorage
from app.services.loaders import registry

logger = logging.getLogger(__name__)
GLOBAL_RULE_SETTING_KEY = "global_rule_prompt"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContractReviewProcessor:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.storage = ContractReviewStorage(settings)

    def run(self, job_id: str) -> None:
        job = self.db.scalar(
            select(ContractReviewJob)
            .options(
                joinedload(ContractReviewJob.template),
                joinedload(ContractReviewJob.clauses),
                joinedload(ContractReviewJob.findings),
            )
            .where(ContractReviewJob.id == job_id)
        )
        if job is None:
            return

        try:
            job.status = ContractReviewJobStatus.running.value
            job.failure_reason = None
            job.updated_at = utcnow()
            self.db.commit()

            file_path = self.storage.resolve_relative_path(job.storage_path)
            load_result = registry.load_document(file_path)
            parsed_clauses = parse_clauses(load_result.fragments)
            template_mode = str(job.template.config_json.get("template_mode", "legacy"))
            if template_mode == "xlsx_checklist":
                global_rule_prompt = self._get_global_rule_prompt()
                findings, summary, overview = ContractReviewLLMAnalyzer(
                    self.settings
                ).analyze(
                    clauses=parsed_clauses,
                    config=job.template.config_json,
                    global_rule_prompt=global_rule_prompt,
                    review_name=job.review_name,
                    original_filename=job.original_filename,
                )
            else:
                findings, summary, overview = analyze_contract(
                    clauses=parsed_clauses,
                    config=job.template.config_json,
                    review_name=job.review_name,
                    original_filename=job.original_filename,
                )

            for finding in list(job.findings):
                self.db.delete(finding)
            for clause in list(job.clauses):
                self.db.delete(clause)
            self.db.flush()

            clause_records: list[ContractReviewClause] = []
            for clause in parsed_clauses:
                record = ContractReviewClause(
                    review_job_id=job.id,
                    clause_path=clause.clause_path,
                    title=clause.title,
                    clause_index=clause.clause_index,
                    page_start=clause.page_start,
                    page_end=clause.page_end,
                    content=clause.content,
                    metadata_json=clause.metadata,
                )
                self.db.add(record)
                clause_records.append(record)
            self.db.flush()

            for order, finding in enumerate(findings):
                clause_id = None
                if finding.clause_index is not None and finding.clause_index < len(
                    clause_records
                ):
                    clause_id = clause_records[finding.clause_index].id
                self.db.add(
                    ContractReviewFinding(
                        review_job_id=job.id,
                        clause_id=clause_id,
                        checklist_key=finding.checklist_key,
                        title=finding.title,
                        severity=finding.severity,
                        status=finding.status,
                        issue=finding.issue,
                        evidence=finding.evidence,
                        rewrite_suggestion=finding.rewrite_suggestion,
                        sort_order=order,
                        metadata_json=finding.metadata,
                    )
                )

            export_path = self.storage.build_export_path(job.id)
            export_location = (
                str(export_path.relative_to(self.settings.backend_root))
                if export_path.is_relative_to(self.settings.backend_root)
                else str(export_path)
            )
            job.summary_json = summary
            job.result_snapshot_json = {
                "overview": overview,
                "template_name": job.template.name,
                "template_profile": job.template.config_json.get("profile", "general"),
                "template_mode": template_mode,
                "export_path": export_location,
                "extensions": {
                    "compare_versions": {"enabled": False, "label": "即将支持"},
                    "review_roles": {"enabled": False, "label": "即将支持"},
                    "law_linkage": {"enabled": False, "label": "即将支持"},
                },
            }
            job.metadata_json = {
                **job.metadata_json,
                "loader_name": load_result.loader_name,
                "raw_doc_count": len(load_result.fragments),
                "review_engine": "llm" if template_mode == "xlsx_checklist" else "rule",
            }
            self.db.commit()

            refreshed_job = self.db.scalar(
                select(ContractReviewJob)
                .options(
                    joinedload(ContractReviewJob.template),
                    joinedload(ContractReviewJob.clauses),
                    joinedload(ContractReviewJob.findings),
                )
                .where(ContractReviewJob.id == job.id)
            )
            if refreshed_job is None:
                return

            build_review_report(
                job=refreshed_job,
                clauses=list(refreshed_job.clauses),
                findings=list(refreshed_job.findings),
                output_path=export_path,
            )

            refreshed_job.status = ContractReviewJobStatus.completed.value
            refreshed_job.completed_at = utcnow()
            refreshed_job.updated_at = utcnow()
            self.db.commit()
        except Exception as exc:
            logger.exception(
                "Contract review job failed",
                extra={"event": "contract_review_job_failed", "job_id": job_id},
            )
            self.db.rollback()
            failed_job = self.db.scalar(
                select(ContractReviewJob).where(ContractReviewJob.id == job_id)
            )
            if failed_job is None:
                return
            failed_job.status = ContractReviewJobStatus.failed.value
            failed_job.failure_reason = str(exc)
            failed_job.completed_at = utcnow()
            failed_job.updated_at = utcnow()
            self.db.commit()

    def _get_global_rule_prompt(self) -> str:
        from app.models import ContractReviewSetting

        setting = self.db.scalar(
            select(ContractReviewSetting).where(
                ContractReviewSetting.key == GLOBAL_RULE_SETTING_KEY
            )
        )
        if setting is None or not setting.value_text:
            return ""
        return setting.value_text
