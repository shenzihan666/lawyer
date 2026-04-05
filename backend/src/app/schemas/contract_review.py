from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReviewTemplateItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str
    contract_type: str
    description: str | None
    source_type: str
    original_filename: str
    stored_filename: str
    storage_path: str
    file_extension: str
    mime_type: str | None
    sha256: str
    file_size: int
    is_active: bool
    config_json: dict[str, Any]
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class ReviewTemplateListResponse(BaseModel):
    items: list[ReviewTemplateItem]


class ReviewTemplateOperationResponse(ReviewTemplateListResponse):
    affected_ids: list[str] = Field(default_factory=list)


class ReviewJobItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    template_id: str
    review_name: str
    status: str
    original_filename: str
    stored_filename: str
    storage_path: str
    file_extension: str
    mime_type: str | None
    sha256: str
    file_size: int
    summary_json: dict[str, Any]
    result_snapshot_json: dict[str, Any]
    metadata_json: dict[str, Any]
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    template_name: str | None = None


class ReviewClauseItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    review_job_id: str
    clause_path: str
    title: str
    clause_index: int
    page_start: int
    page_end: int
    content: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ReviewFindingItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    review_job_id: str
    clause_id: int | None
    checklist_key: str
    title: str
    severity: str
    status: str
    issue: str
    evidence: str | None
    rewrite_suggestion: str | None
    sort_order: int
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    clause_title: str | None = None
    clause_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None


class ReviewChecklistSummary(BaseModel):
    total: int = 0
    passed: int = 0
    warnings: int = 0
    failed: int = 0
    missing: int = 0
    high_risk: int = 0
    medium_risk: int = 0
    low_risk: int = 0


class ReviewExportStatus(BaseModel):
    available: bool = False
    filename: str | None = None
    url: str | None = None


class ReviewJobDetailResponse(BaseModel):
    job: ReviewJobItem
    template: ReviewTemplateItem | None = None
    clauses: list[ReviewClauseItem] = Field(default_factory=list)
    findings: list[ReviewFindingItem] = Field(default_factory=list)
    checklist: ReviewChecklistSummary = Field(default_factory=ReviewChecklistSummary)
    export: ReviewExportStatus = Field(default_factory=ReviewExportStatus)
    extensions: dict[str, Any] = Field(default_factory=dict)


class ReviewJobListResponse(BaseModel):
    items: list[ReviewJobItem]
