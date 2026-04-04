import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentIngestionStatus(str, enum.Enum):
    processing = "processing"
    ready = "ready"
    failed = "failed"
    deleted = "deleted"


class DocumentVectorStatus(str, enum.Enum):
    not_requested = "not_requested"
    queued = "queued"
    indexing = "indexing"
    indexed = "indexed"
    failed = "failed"


class DocumentAsset(Base):
    __tablename__ = "document_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(512))
    file_extension: Mapped[str] = mapped_column(String(16))
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    loader_name: Mapped[str] = mapped_column(String(64), default="pending")
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    preview_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_status: Mapped[str] = mapped_column(
        String(32),
        default=DocumentIngestionStatus.processing.value,
    )
    vector_status: Mapped[str] = mapped_column(
        String(32),
        default=DocumentVectorStatus.not_requested.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    fragments: Mapped[list["DocumentFragment"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentFragment.fragment_index",
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_level, DocumentChunk.chunk_index",
    )


class DocumentFragment(Base):
    __tablename__ = "document_fragments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("document_assets.id", ondelete="CASCADE"),
        index=True,
    )
    fragment_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    fragment_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    document: Mapped[DocumentAsset] = relationship(back_populates="fragments")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("document_assets.id", ondelete="CASCADE"),
        index=True,
    )
    root_chunk_id: Mapped[str] = mapped_column(String(128), index=True)
    parent_chunk_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_level: Mapped[int] = mapped_column(Integer, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    document: Mapped[DocumentAsset] = relationship(back_populates="chunks")
