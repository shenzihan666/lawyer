from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OpponentAnalysisCitation(BaseModel):
    citation_number: int
    chunk_id: str
    document_id: str
    original_filename: str
    page_number: int = 0
    snippet: str
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpponentAnalysisAgentPayload(BaseModel):
    claims: list[str] = Field(default_factory=list)
    likely_quotes: list[str] = Field(default_factory=list)
    likely_actions: list[str] = Field(default_factory=list)
    attack_points: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    notes: str = ""
    citation_numbers: list[int] = Field(default_factory=list)


class OpponentAnalysisResponsePlan(BaseModel):
    priority_actions: list[str] = Field(default_factory=list)
    courtroom_responses: list[str] = Field(default_factory=list)
    evidence_to_prepare: list[str] = Field(default_factory=list)
    notes: str = ""


class OpponentAnalysisEvidenceItem(BaseModel):
    citation_number: int
    chunk_id: str
    document_id: str
    original_filename: str
    page_number: int = 0
    snippet: str
    score: float = 0.0
    used_by: list[str] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpponentAnalysisOpponentPosition(BaseModel):
    summary: str = ""
    claims: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class OpponentAnalysisSummary(BaseModel):
    opponent_position: OpponentAnalysisOpponentPosition = Field(
        default_factory=OpponentAnalysisOpponentPosition,
    )
    lawyer_predictions: OpponentAnalysisAgentPayload = Field(
        default_factory=OpponentAnalysisAgentPayload,
    )
    party_predictions: OpponentAnalysisAgentPayload = Field(
        default_factory=OpponentAnalysisAgentPayload,
    )
    response_plan: OpponentAnalysisResponsePlan = Field(
        default_factory=OpponentAnalysisResponsePlan,
    )
    evidence_index: list[OpponentAnalysisEvidenceItem] = Field(default_factory=list)
    risk_level: str = "pending"


class OpponentAnalysisRunCreateRequest(BaseModel):
    case_facts: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    document_ids: list[str] = Field(default_factory=list)


class OpponentAnalysisRunItem(BaseModel):
    id: str
    case_facts: str
    case_facts_preview: str
    top_k: int
    scope_document_ids: list[str] = Field(default_factory=list)
    status: str
    risk_level: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class OpponentAnalysisEventItem(BaseModel):
    id: int
    seq: int
    phase: str
    round: int
    from_agent: str | None = None
    to_agent: str | None = None
    event_type: str
    title: str
    content: str
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    citations: list[OpponentAnalysisCitation] = Field(default_factory=list)
    status: str
    created_at: datetime


class OpponentAnalysisListResponse(BaseModel):
    items: list[OpponentAnalysisRunItem] = Field(default_factory=list)


class OpponentAnalysisDetailResponse(BaseModel):
    run: OpponentAnalysisRunItem
    events: list[OpponentAnalysisEventItem] = Field(default_factory=list)
    summary: OpponentAnalysisSummary = Field(default_factory=OpponentAnalysisSummary)


class OpponentAnalysisStreamSnapshot(BaseModel):
    run: OpponentAnalysisRunItem
    summary: OpponentAnalysisSummary = Field(default_factory=OpponentAnalysisSummary)
    latest_seq: int = 0
