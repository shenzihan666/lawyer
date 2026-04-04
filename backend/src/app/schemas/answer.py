from typing import Any

from pydantic import BaseModel, Field


class AnswerRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    document_ids: list[str] = Field(default_factory=list)


class AnswerCitation(BaseModel):
    citation_number: int
    chunk_id: str
    document_id: str
    root_chunk_id: str
    parent_chunk_id: str | None = None
    chunk_level: int
    chunk_index: int
    page_number: int = 0
    original_filename: str
    snippet: str
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnswerResponse(BaseModel):
    answer: str
    citations: list[AnswerCitation] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
