from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CaseSearchQueryAsset(Base):
    __tablename__ = "case_search_query_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(512))
    preview_storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_extension: Mapped[str] = mapped_column(String(16))
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    extraction_status: Mapped[str] = mapped_column(String(32), default="ready")
    preview_status: Mapped[str] = mapped_column(String(32), default="not_requested")
    preview_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    searches: Mapped[list["CaseSearchRecord"]] = relationship(
        back_populates="query_asset"
    )


class CaseSearchRecord(Base):
    __tablename__ = "case_search_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query_type: Mapped[str] = mapped_column(String(16))
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    prepared_query: Mapped[str] = mapped_column(Text)
    top_k: Mapped[int] = mapped_column(Integer, default=5)
    scope_document_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    query_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_search_query_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="completed")
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    query_asset: Mapped[CaseSearchQueryAsset | None] = relationship(
        back_populates="searches"
    )
    hits: Mapped[list["CaseSearchHit"]] = relationship(
        back_populates="search",
        cascade="all, delete-orphan",
        order_by="CaseSearchHit.rank",
    )


class CaseSearchHit(Base):
    __tablename__ = "case_search_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_id: Mapped[str] = mapped_column(
        ForeignKey("case_search_records.id", ondelete="CASCADE"),
        index=True,
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("document_assets.id", ondelete="CASCADE"),
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    matched_chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_pages_json: Mapped[list[int]] = mapped_column(JSON, default=list)
    matched_chunk_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    matched_snippets_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    hit_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    search: Mapped[CaseSearchRecord] = relationship(back_populates="hits")
