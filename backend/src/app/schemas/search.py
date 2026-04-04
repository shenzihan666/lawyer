from typing import Any

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    document_ids: list[str] = Field(default_factory=list)


class SearchResultItem(BaseModel):
    chunk_id: str
    document_id: str
    root_chunk_id: str
    parent_chunk_id: str | None = None
    chunk_level: int
    chunk_index: int
    page_number: int = 0
    content: str
    original_filename: str
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    items: list[SearchResultItem] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
