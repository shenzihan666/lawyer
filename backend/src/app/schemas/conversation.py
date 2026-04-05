from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationResponse(BaseModel):
    thread_id: str
    title: str
    message_count: int = 0
    last_message_preview: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]


class ConversationUpdate(BaseModel):
    title: str | None = None


class AgentChatRequest(BaseModel):
    query: str = Field(min_length=1)
    thread_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=10)
    document_ids: list[str] = Field(default_factory=list)


class MessageItem(BaseModel):
    role: str
    content: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class MessageListResponse(BaseModel):
    thread_id: str
    messages: list[MessageItem]
