from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    stored_filename: str
    storage_path: str
    file_extension: str
    mime_type: str | None
    loader_name: str
    sha256: str
    file_size: int
    page_count: int
    raw_doc_count: int
    preview_excerpt: str | None
    ingestion_status: str
    vector_status: str
    failure_reason: str | None
    trace_metadata: dict[str, Any]
    uploaded_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class DocumentSummary(BaseModel):
    total: int = 0
    ready: int = 0
    failed: int = 0
    vector_queued: int = 0
    deleted: int = 0


class DocumentListResponse(BaseModel):
    items: list[DocumentItem]
    summary: DocumentSummary


class DocumentOperationResponse(DocumentListResponse):
    affected_ids: list[str] = Field(default_factory=list)


class BatchDeleteRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list, min_length=1)


class VectorizeRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list, min_length=1)
