from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.models import (
    ContractReviewFinding,
    ContractReviewJob,
    ContractReviewJobStatus,
    ContractReviewSetting,
    ContractReviewTemplate,
    ContractReviewTemplateSource,
)
from app.schemas.contract_review import (
    ReviewChecklistSummary,
    ReviewClauseItem,
    ReviewExportStatus,
    ReviewFindingItem,
    ReviewJobDetailResponse,
    ReviewJobItem,
    ReviewJobListResponse,
    ReviewJobOperationResponse,
    ReviewSettingsResponse,
    ReviewTemplateItem,
    ReviewTemplateListResponse,
    ReviewTemplateOperationResponse,
)
from app.services.contract_review.checklist_parser import (
    ChecklistTemplateParseError,
    ParsedChecklistTemplate,
    parse_checklist_template,
)
from app.services.contract_review.executor import submit_review_job
from app.services.contract_review.profiles import get_profile_config
from app.services.contract_review.storage import ContractReviewStorage
from app.services.loaders import registry
from app.services.loaders.base import UnsupportedDocumentTypeError


GLOBAL_RULE_SETTING_KEY = "global_rule_prompt"


class ContractReviewService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.storage = ContractReviewStorage(settings)

    def list_templates(self) -> ReviewTemplateListResponse:
        items = [
            self._to_template_item(template) for template in self._fetch_templates()
        ]
        return ReviewTemplateListResponse(items=items)

    def get_settings(self) -> ReviewSettingsResponse:
        return ReviewSettingsResponse(global_rule_prompt=self._get_global_rule_prompt())

    def update_settings(self, *, global_rule_prompt: str) -> ReviewSettingsResponse:
        setting = self.db.scalar(
            select(ContractReviewSetting).where(
                ContractReviewSetting.key == GLOBAL_RULE_SETTING_KEY
            )
        )
        if setting is None:
            setting = ContractReviewSetting(
                key=GLOBAL_RULE_SETTING_KEY,
                value_text=global_rule_prompt.strip(),
            )
            self.db.add(setting)
        else:
            setting.value_text = global_rule_prompt.strip()
        self.db.commit()
        return ReviewSettingsResponse(global_rule_prompt=setting.value_text or "")

    def upload_template(
        self,
        *,
        file: UploadFile,
        name: str,
        category: str,
        contract_type: str,
        description: str | None,
        config_profile: str,
    ) -> ReviewTemplateOperationResponse:
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Template file is missing a filename.",
            )

        self._ensure_template_upload_supported(file.filename)
        stored_file = self.storage.save_upload(file, "templates")

        duplicate = self.db.scalar(
            select(ContractReviewTemplate).where(
                ContractReviewTemplate.sha256 == stored_file.sha256_digest,
                ContractReviewTemplate.deleted_at.is_(None),
            )
        )
        if duplicate is not None:
            self.storage.delete_file(stored_file.relative_path)
            return ReviewTemplateOperationResponse(
                items=[
                    self._to_template_item(template)
                    for template in self._fetch_templates()
                ],
                affected_ids=[duplicate.id],
            )

        try:
            parsed_template = parse_checklist_template(stored_file.absolute_path)
        except ChecklistTemplateParseError as exc:
            self.storage.delete_file(stored_file.relative_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        resolved_name = name.strip() or Path(file.filename).stem
        template = ContractReviewTemplate(
            id=stored_file.asset_id,
            name=resolved_name,
            category=category.strip() or parsed_template.sheet_name or "Excel 审查清单",
            contract_type=contract_type.strip() or "xlsx_checklist",
            description=description.strip()
            if description
            else self._derive_template_description(parsed_template),
            source_type=ContractReviewTemplateSource.manual.value,
            original_filename=stored_file.original_filename,
            stored_filename=stored_file.stored_filename,
            storage_path=stored_file.relative_path,
            file_extension=stored_file.file_extension,
            mime_type=stored_file.mime_type,
            sha256=stored_file.sha256_digest,
            file_size=stored_file.file_size,
            is_active=True,
            config_json=self._build_template_config(parsed_template, resolved_name),
            metadata_json={
                "template_mode": "xlsx_checklist",
                "sheet_name": parsed_template.sheet_name,
                "checklist_count": len(parsed_template.checklist),
                "config_profile": config_profile,
            },
        )
        self.db.add(template)
        self.db.commit()
        return ReviewTemplateOperationResponse(
            items=[self._to_template_item(item) for item in self._fetch_templates()],
            affected_ids=[template.id],
        )

    def delete_template(self, template_id: str) -> ReviewTemplateOperationResponse:
        template = self._get_template(template_id)
        template.deleted_at = self._utcnow()
        template.is_active = False
        self.db.commit()
        return ReviewTemplateOperationResponse(
            items=[self._to_template_item(item) for item in self._fetch_templates()],
            affected_ids=[template_id],
        )

    def list_jobs(self) -> ReviewJobListResponse:
        self.db.expire_all()
        items = [self._to_job_item(job) for job in self._fetch_jobs()]
        return ReviewJobListResponse(items=items)

    def create_job(
        self,
        *,
        file: UploadFile,
        template_id: str,
        review_name: str | None,
    ) -> ReviewJobDetailResponse:
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Review file is missing a filename.",
            )

        template = self._get_template(template_id)
        self._get_loader_name_for_upload(file.filename)
        stored_file = self.storage.save_upload(file, "reviews")
        resolved_review_name = (
            review_name.strip() if review_name else Path(file.filename).stem
        )
        template_mode = str(template.config_json.get("template_mode", "legacy"))
        job = ContractReviewJob(
            id=str(uuid4()),
            template_id=template.id,
            review_name=resolved_review_name,
            status=ContractReviewJobStatus.queued.value,
            original_filename=stored_file.original_filename,
            stored_filename=stored_file.stored_filename,
            storage_path=stored_file.relative_path,
            file_extension=stored_file.file_extension,
            mime_type=stored_file.mime_type,
            sha256=stored_file.sha256_digest,
            file_size=stored_file.file_size,
            summary_json={},
            result_snapshot_json={
                "overview": {
                    "title": template.config_json.get("report_title", "合同审查报告"),
                    "review_name": resolved_review_name,
                    "original_filename": stored_file.original_filename,
                    "contract_type": template.contract_type,
                    "clause_count": 0,
                    "highlights": ["任务已创建，正在等待系统完成结构化审查。"],
                },
                "template_name": template.name,
                "template_profile": template.config_json.get("profile", template_mode),
                "template_mode": template_mode,
                "extensions": {
                    "compare_versions": {"enabled": False, "label": "即将支持"},
                    "review_roles": {"enabled": False, "label": "即将支持"},
                    "law_linkage": {"enabled": False, "label": "即将支持"},
                },
            },
            metadata_json={
                "template_category": template.category,
                "template_mode": template_mode,
            },
        )
        self.db.add(job)
        self.db.commit()
        submit_review_job(job.id)
        return self.get_job_detail(job.id)

    def get_job_detail(self, job_id: str) -> ReviewJobDetailResponse:
        self.db.expire_all()
        job = self._get_job(job_id, with_detail=True)

        export_path = job.result_snapshot_json.get("export_path")
        export_available = False
        if export_path:
            export_available = self.storage.resolve_relative_path(export_path).exists()

        clause_lookup = {clause.clause_path: clause for clause in job.clauses}
        return ReviewJobDetailResponse(
            job=self._to_job_item(job),
            template=self._to_template_item(job.template) if job.template else None,
            clauses=[ReviewClauseItem.model_validate(clause) for clause in job.clauses],
            findings=[
                self._to_finding_item(finding, clause_lookup=clause_lookup)
                for finding in job.findings
            ],
            checklist=ReviewChecklistSummary(**job.summary_json)
            if job.summary_json
            else ReviewChecklistSummary(),
            export=ReviewExportStatus(
                available=export_available
                and job.status == ContractReviewJobStatus.completed.value,
                filename=f"{job.review_name}.docx" if export_available else None,
                url=f"{self.settings.api_v1_prefix}/contract-review/jobs/{job.id}/export.docx"
                if export_available
                else None,
            ),
            extensions=job.result_snapshot_json.get("extensions", {}),
        )

    def delete_job(self, job_id: str) -> ReviewJobOperationResponse:
        job = self._get_job(job_id)
        if job.status in {
            ContractReviewJobStatus.queued.value,
            ContractReviewJobStatus.running.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Running review jobs cannot be removed yet.",
            )

        export_path = job.result_snapshot_json.get("export_path")
        if isinstance(export_path, str) and export_path:
            self.storage.delete_file(export_path)
        self.storage.delete_file(job.storage_path)

        self.db.delete(job)
        self.db.commit()

        return ReviewJobOperationResponse(
            items=[self._to_job_item(item) for item in self._fetch_jobs()],
            affected_ids=[job_id],
        )

    def get_export_path(self, job_id: str) -> Path:
        job = self.db.scalar(
            select(ContractReviewJob).where(ContractReviewJob.id == job_id)
        )
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review job not found.",
            )
        if job.status != ContractReviewJobStatus.completed.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Review job has not completed yet.",
            )
        export_path = job.result_snapshot_json.get("export_path")
        if not export_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review export is unavailable.",
            )
        resolved = self.storage.resolve_relative_path(export_path)
        if not resolved.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review export is unavailable.",
            )
        return resolved

    def import_seed_templates(self, manifest_items: Sequence[dict]) -> list[str]:
        affected_ids: list[str] = []
        for item in manifest_items:
            source_path = self.settings.backend_root.parent / item["source_path"]
            if not source_path.exists():
                continue

            self._get_loader_name_for_upload(source_path.name)
            stored_file = self.storage.import_file(
                source_path,
                "templates",
                original_filename=item.get("original_filename") or source_path.name,
            )
            duplicate = self.db.scalar(
                select(ContractReviewTemplate).where(
                    ContractReviewTemplate.sha256 == stored_file.sha256_digest,
                    ContractReviewTemplate.deleted_at.is_(None),
                )
            )
            if duplicate is not None:
                self.storage.delete_file(stored_file.relative_path)
                affected_ids.append(duplicate.id)
                continue

            template = ContractReviewTemplate(
                id=stored_file.asset_id,
                name=item["name"],
                category=item.get("category", "通用合同"),
                contract_type=item.get("contract_type", "general"),
                description=item.get("description"),
                source_type=ContractReviewTemplateSource.seed.value,
                original_filename=stored_file.original_filename,
                stored_filename=stored_file.stored_filename,
                storage_path=stored_file.relative_path,
                file_extension=stored_file.file_extension,
                mime_type=stored_file.mime_type,
                sha256=stored_file.sha256_digest,
                file_size=stored_file.file_size,
                is_active=True,
                config_json=get_profile_config(item.get("config_profile", "general")),
                metadata_json={
                    "config_profile": item.get("config_profile", "general"),
                    "seed_source_path": item["source_path"],
                },
            )
            self.db.add(template)
            self.db.commit()
            affected_ids.append(template.id)

        return affected_ids

    def _fetch_templates(self) -> list[ContractReviewTemplate]:
        return list(
            self.db.scalars(
                select(ContractReviewTemplate)
                .where(ContractReviewTemplate.deleted_at.is_(None))
                .order_by(ContractReviewTemplate.created_at.desc())
            )
        )

    def _fetch_jobs(self) -> list[ContractReviewJob]:
        return list(
            self.db.scalars(
                select(ContractReviewJob)
                .options(joinedload(ContractReviewJob.template))
                .order_by(ContractReviewJob.created_at.desc())
            )
        )

    def _get_template(self, template_id: str) -> ContractReviewTemplate:
        template = self.db.scalar(
            select(ContractReviewTemplate).where(
                ContractReviewTemplate.id == template_id
            )
        )
        if (
            template is None
            or template.deleted_at is not None
            or not template.is_active
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review template not found.",
            )
        return template

    def _get_job(self, job_id: str, *, with_detail: bool = False) -> ContractReviewJob:
        statement = select(ContractReviewJob)
        if with_detail:
            statement = statement.options(
                joinedload(ContractReviewJob.template),
                joinedload(ContractReviewJob.clauses),
                joinedload(ContractReviewJob.findings).joinedload(
                    ContractReviewFinding.clause
                ),
            )
        else:
            statement = statement.options(joinedload(ContractReviewJob.template))

        job = self.db.scalar(statement.where(ContractReviewJob.id == job_id))
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review job not found.",
            )
        return job

    def _to_template_item(self, template: ContractReviewTemplate) -> ReviewTemplateItem:
        return ReviewTemplateItem.model_validate(template)

    def _to_job_item(self, job: ContractReviewJob) -> ReviewJobItem:
        data = ReviewJobItem.model_validate(job).model_dump()
        data["template_name"] = job.template.name if job.template else None
        return ReviewJobItem(**data)

    def _to_finding_item(
        self,
        finding: ContractReviewFinding,
        *,
        clause_lookup: dict[str, object],
    ) -> ReviewFindingItem:
        payload = ReviewFindingItem.model_validate(finding).model_dump()
        payload["clause_title"] = finding.clause.title if finding.clause else None
        payload["clause_path"] = finding.clause.clause_path if finding.clause else None
        payload["page_start"] = finding.clause.page_start if finding.clause else None
        payload["page_end"] = finding.clause.page_end if finding.clause else None

        metadata_json = dict(finding.metadata_json or {})
        payload["checklist_item"] = metadata_json.get("checklist_item") or {}

        evidence_items: list[dict] = []
        for item in metadata_json.get("evidence_items", []) or []:
            if not isinstance(item, dict):
                continue
            clause = clause_lookup.get(str(item.get("clause_path", "")))
            evidence_items.append(
                {
                    "clause_id": getattr(clause, "id", None),
                    "clause_path": item.get("clause_path"),
                    "clause_title": item.get("clause_title"),
                    "excerpt": item.get("excerpt"),
                    "page_start": item.get("page_start"),
                    "page_end": item.get("page_end"),
                }
            )
        payload["evidence_items"] = evidence_items
        return ReviewFindingItem(**payload)

    def _get_global_rule_prompt(self) -> str:
        setting = self.db.scalar(
            select(ContractReviewSetting).where(
                ContractReviewSetting.key == GLOBAL_RULE_SETTING_KEY
            )
        )
        if setting is None or not setting.value_text:
            return ""
        return setting.value_text

    @staticmethod
    def _build_template_config(
        parsed_template: ParsedChecklistTemplate,
        template_name: str,
    ) -> dict[str, object]:
        return {
            "template_mode": "xlsx_checklist",
            "profile": "xlsx_checklist",
            "report_title": f"{template_name}审查报告",
            "sheet_name": parsed_template.sheet_name,
            "template_name": template_name,
            "applicability": parsed_template.applicability,
            "checklist": [
                {
                    "key": item.key,
                    "title": item.title,
                    "risk_level": item.risk_level,
                    "description": item.description,
                    "related_clauses": item.related_clauses,
                    "related_knowledge_points": item.related_knowledge_points,
                    "source_block_text": item.source_block_text,
                }
                for item in parsed_template.checklist
            ],
        }

    @staticmethod
    def _derive_template_description(
        parsed_template: ParsedChecklistTemplate,
    ) -> str | None:
        if parsed_template.applicability:
            return parsed_template.applicability[0]
        return None

    @staticmethod
    def _ensure_template_upload_supported(filename: str) -> None:
        suffix = Path(filename).suffix.lower()
        if suffix != ".xlsx":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Checklist uploads only support .xlsx files.",
            )

    @staticmethod
    def _get_loader_name_for_upload(filename: str) -> str:
        try:
            return registry.get_loader_name_for_suffix(Path(filename).suffix.lower())
        except UnsupportedDocumentTypeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @staticmethod
    def _utcnow():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
