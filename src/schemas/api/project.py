"""
Pydantic schemas for the Projects API.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Paper summary (used inside project source lists)
# ---------------------------------------------------------------------------


class ProjectPaperSummary(BaseModel):
    """Lightweight paper card — enough for the frontend source panel."""

    id: UUID
    source: str                               # "arxiv" | "user_upload"
    arxiv_id: Optional[str] = None
    original_filename: Optional[str] = None
    title: str
    authors: List[str]
    abstract: str
    categories: List[str]
    published_date: datetime
    pdf_processed: bool
    added_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Project CRUD schemas
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    """Lean response for list views — no sources, no messages."""

    id: UUID
    name: str
    description: Optional[str] = None
    overview: Optional[str] = None
    source_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectDetailResponse(BaseModel):
    """Full project detail including sources and overview."""

    id: UUID
    name: str
    description: Optional[str] = None
    overview: Optional[str] = None
    overview_generated_at: Optional[datetime] = None
    sources: List[ProjectPaperSummary] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Source management schemas
# ---------------------------------------------------------------------------


class AddSourceRequest(BaseModel):
    paper_id: UUID = Field(
        ...,
        description=(
            "Internal paper UUID (papers.id). Works for both arxiv papers "
            "and user uploads — use the `id` field from any paper response."
        ),
    )


class AddSourceResponse(BaseModel):
    project_id: UUID
    paper_id: UUID
    added_at: datetime
    paper: ProjectPaperSummary


# ---------------------------------------------------------------------------
# Project chat schemas
# ---------------------------------------------------------------------------


class ProjectChatMessageResponse(BaseModel):
    id: UUID
    project_id: UUID
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectChatHistoryResponse(BaseModel):
    project_id: UUID
    messages: List[ProjectChatMessageResponse]


# ---------------------------------------------------------------------------
# Project-scoped ask schemas
# Project ID comes from the URL so it's not in the request body.
# ---------------------------------------------------------------------------


class ProjectAskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=50)
    use_hybrid: bool = Field(default=True)
    model: str = Field(default="meta/llama-3.3-70b-instruct")
    categories: Optional[List[str]] = None


class ProjectAskResponse(BaseModel):
    query: str
    answer: str
    sources: List[str]
    chunks_used: int
    search_mode: str
    project_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
