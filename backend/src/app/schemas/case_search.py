from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CaseSearchMatchedChunk(BaseModel):
    chunk_id: str
    page_number: int = 0
    score: float = 0.0
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseSearchQueryAssetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    file_extension: str
    mime_type: str | None
    file_size: int
    extraction_status: str
    preview_status: str
    preview_excerpt: str | None = None
    created_at: datetime


class CaseSearchListItem(BaseModel):
    id: str
    query_type: str
    query_text: str | None = None
    prepared_query: str
    top_k: int
    scope_document_ids: list[str] = Field(default_factory=list)
    status: str
    result_count: int
    query_asset: CaseSearchQueryAssetSummary | None = None
    created_at: datetime
    updated_at: datetime


class CaseSearchHitItem(BaseModel):
    id: int
    document_id: str
    original_filename: str
    preview_excerpt: str | None = None
    rank: int
    score: float
    matched_chunk_count: int
    matched_pages: list[int] = Field(default_factory=list)
    matched_chunk_ids: list[str] = Field(default_factory=list)
    matched_snippets: list[str] = Field(default_factory=list)
    top_chunks: list[CaseSearchMatchedChunk] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class CaseSearchDetailResponse(BaseModel):
    item: CaseSearchListItem
    hits: list[CaseSearchHitItem] = Field(default_factory=list)


class CaseSearchListResponse(BaseModel):
    items: list[CaseSearchListItem] = Field(default_factory=list)
