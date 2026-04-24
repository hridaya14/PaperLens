"""
Pydantic schemas for the general chat sessions API.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Message schemas
# ---------------------------------------------------------------------------


class ChatMessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Session schemas
# ---------------------------------------------------------------------------


class ChatSessionResponse(BaseModel):
    """Lean session — for list views. No messages included."""

    id: UUID
    title: Optional[str] = None  # None until first message
    message_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatSessionDetailResponse(BaseModel):
    """Full session with message history."""

    id: UUID
    title: Optional[str] = None
    messages: List[ChatMessageResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RenameSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


# ---------------------------------------------------------------------------
# Session-scoped ask schemas
# Session ID comes from the URL — not in the request body.
# ---------------------------------------------------------------------------


class SessionAskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=50)
    use_hybrid: bool = Field(default=True)
    model: str = Field(default="meta/llama-3.3-70b-instruct")
    categories: Optional[List[str]] = None


class SessionAskResponse(BaseModel):
    query: str
    answer: str
    sources: List[str]
    chunks_used: int
    search_mode: str
    session_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    metrics: Optional[Dict[str, Any]] = None
