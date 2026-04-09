"""
Schemas for the paper upload API.

Kept separate from arxiv/paper.py intentionally — uploads have a different
shape (no arxiv_id, different required fields) and shouldn't pollute the
existing ArXiv schemas.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class UploadStatus(str, Enum):
    """Lifecycle states of a background upload task."""

    PENDING = "pending"  # Task accepted, not started yet
    PROCESSING = "processing"  # Parsing / embedding / indexing in progress
    COMPLETED = "completed"  # All steps done, paper_id available
    FAILED = "failed"  # Unrecoverable error, see `error` field


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


class UploadMetadata(BaseModel):
    """
    Optional JSON metadata the client can send alongside the PDF.

    All fields are optional — if the client omits them we fall back to
    whatever Docling can extract from the document itself.
    """

    title: Optional[str] = Field(None, description="Paper title (overrides extracted title)")
    authors: Optional[List[str]] = Field(None, description="Author list")
    abstract: Optional[str] = Field(None, description="Abstract text")
    categories: Optional[List[str]] = Field(None, description="Custom tags / topic categories")
    published_date: Optional[datetime] = Field(None, description="Publication date (ISO 8601). Defaults to upload time.")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class UploadAcceptedResponse(BaseModel):
    """
    Returned immediately (HTTP 202) when the file is accepted.

    The client should poll GET /uploads/{task_id}/status until
    status == 'completed' or 'failed'.
    """

    task_id: str = Field(..., description="Unique ID for polling upload status")
    message: str = Field(
        "File accepted. Processing in background.",
        description="Human-readable confirmation",
    )


class UploadStatusResponse(BaseModel):
    """
    Returned by the status-polling endpoint.

    `paper_id` is populated only when status == 'completed'.
    `error`    is populated only when status == 'failed'.
    `progress` is a free-form dict for optional UI progress bars
               (e.g. {"step": "embedding", "chunks_done": 12, "chunks_total": 40}).
    """

    task_id: str
    status: UploadStatus
    paper_id: Optional[UUID] = Field(None, description="DB paper ID, available on completion")
    original_filename: Optional[str] = None
    progress: Optional[Dict[str, Any]] = Field(None, description="Optional progress information")
    error: Optional[str] = Field(None, description="Error message if status == failed")
    created_at: datetime
    updated_at: datetime


class UploadedPaperResponse(BaseModel):
    """
    Full paper detail returned via GET /uploads/{paper_id}/detail.

    Mirrors PaperResponse but exposes the upload-specific fields
    (source, original_filename, uploaded_at) that PaperResponse omits.
    """

    id: UUID
    source: str
    original_filename: Optional[str] = None
    uploaded_at: Optional[datetime] = None

    title: str
    authors: List[str]
    abstract: str
    categories: List[str]
    published_date: datetime
    pdf_url: str

    # Parsed content
    raw_text: Optional[str] = None
    sections: Optional[List[Dict[str, Any]]] = None

    # Processing metadata
    pdf_processed: bool
    pdf_processing_date: Optional[datetime] = None
    parser_used: Optional[str] = None

    # Indexing stats (populated after background task completes)
    chunks_indexed: Optional[int] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
