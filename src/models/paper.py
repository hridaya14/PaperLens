import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, CheckConstraint, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from src.db.interfaces.postgresql import Base


class Paper(Base):
    __tablename__ = "papers"

    # Full-text search vector
    search_vector = Column(TSVECTOR)

    # Table-level constraints and indexes
    __table_args__ = (
        # GIN index for full-text search
        Index(
            "ix_papers_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
        # Check constraint: arxiv papers must have arxiv_id
        CheckConstraint("source != 'arxiv' OR arxiv_id IS NOT NULL", name="check_arxiv_has_id"),
    )

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source tracking (NEW)
    source = Column(String(20), nullable=False, default="arxiv", index=True, comment="Source of paper: arxiv or user_upload")

    # Original filename for uploads (NEW)
    original_filename = Column(Text, nullable=True, comment="Original filename for user uploads")

    # Upload timestamp (NEW)
    uploaded_at = Column(DateTime, nullable=True, comment="Timestamp when paper was uploaded")

    # Core arXiv metadata (arxiv_id now nullable for user uploads)
    arxiv_id = Column(
        String,
        unique=True,
        nullable=True,  # Changed from NOT NULL to support user uploads
        index=True,
        comment="ArXiv ID (e.g., 2401.12345), NULL for user uploads",
    )
    title = Column(String, nullable=False)
    authors = Column(JSONB, nullable=False)
    abstract = Column(Text, nullable=False)
    categories = Column(JSONB, nullable=False, comment="ArXiv categories or custom tags")
    published_date = Column(DateTime, nullable=False)
    pdf_url = Column(String, nullable=False, comment="ArXiv PDF URL or local storage path")

    # Parsed PDF content
    raw_text = Column(Text, nullable=True)
    sections = Column(JSONB, nullable=True)
    references = Column(JSONB, nullable=True)

    # PDF processing metadata
    parser_used = Column(String, nullable=True)
    parser_metadata = Column(JSONB, nullable=True)
    pdf_processed = Column(Boolean, default=False, nullable=False)
    pdf_processing_date = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self):
        if self.source == "arxiv":
            return f"<Paper(arxiv_id='{self.arxiv_id}', title='{self.title[:50]}...')>"
        else:
            return f"<Paper(user_upload, title='{self.title[:50]}...')>"

    @property
    def is_arxiv(self) -> bool:
        """Check if this is an ArXiv paper."""
        return self.source == "arxiv"

    @property
    def is_user_upload(self) -> bool:
        """Check if this is a user-uploaded paper."""
        return self.source == "user_upload"

    @property
    def display_id(self) -> str:
        """Get display ID (arxiv_id or internal UUID)."""
        return self.arxiv_id if self.arxiv_id else str(self.id)
