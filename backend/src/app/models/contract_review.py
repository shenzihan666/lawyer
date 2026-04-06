import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContractReviewTemplateSource(str, enum.Enum):
    seed = "seed"
    manual = "manual"


class ContractReviewJobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class ContractReviewFindingSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ContractReviewFindingStatus(str, enum.Enum):
    passed = "pass"
    warning = "warn"
    failed = "fail"
    missing = "missing"


class ContractReviewTemplate(Base):
    __tablename__ = "contract_review_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(120), default="通用合同")
    contract_type: Mapped[str] = mapped_column(String(120), default="general")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(16), default=ContractReviewTemplateSource.manual.value
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(512))
    file_extension: Mapped[str] = mapped_column(String(16))
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    jobs: Mapped[list["ContractReviewJob"]] = relationship(back_populates="template")


class ContractReviewSetting(Base):
    __tablename__ = "contract_review_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ContractReviewJob(Base):
    __tablename__ = "contract_review_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("contract_review_templates.id"), index=True
    )
    review_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(32), default=ContractReviewJobStatus.queued.value, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(512))
    file_extension: Mapped[str] = mapped_column(String(16))
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    template: Mapped[ContractReviewTemplate] = relationship(back_populates="jobs")
    clauses: Mapped[list["ContractReviewClause"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="ContractReviewClause.clause_index",
    )
    findings: Mapped[list["ContractReviewFinding"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="ContractReviewFinding.sort_order",
    )


class ContractReviewClause(Base):
    __tablename__ = "contract_review_clauses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_job_id: Mapped[str] = mapped_column(
        ForeignKey("contract_review_jobs.id", ondelete="CASCADE"), index=True
    )
    clause_path: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255))
    clause_index: Mapped[int] = mapped_column(Integer, index=True)
    page_start: Mapped[int] = mapped_column(Integer, default=0)
    page_end: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    job: Mapped[ContractReviewJob] = relationship(back_populates="clauses")
    findings: Mapped[list["ContractReviewFinding"]] = relationship(
        back_populates="clause"
    )


class ContractReviewFinding(Base):
    __tablename__ = "contract_review_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_job_id: Mapped[str] = mapped_column(
        ForeignKey("contract_review_jobs.id", ondelete="CASCADE"), index=True
    )
    clause_id: Mapped[int | None] = mapped_column(
        ForeignKey("contract_review_clauses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    checklist_key: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(
        String(16), default=ContractReviewFindingSeverity.medium.value
    )
    status: Mapped[str] = mapped_column(
        String(16), default=ContractReviewFindingStatus.warning.value
    )
    issue: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    rewrite_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    job: Mapped[ContractReviewJob] = relationship(back_populates="findings")
    clause: Mapped[ContractReviewClause | None] = relationship(
        back_populates="findings"
    )
