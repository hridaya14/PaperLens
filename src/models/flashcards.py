"""
SQLAlchemy model for flashcards (NotebookLM-style).

Multiple flashcards per paper, each covering a specific concept.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from src.db.interfaces.postgresql import Base


class Flashcard(Base):
    __tablename__ = "flashcards"

    # Table-level constraints
    __table_args__ = (
        # Unique constraint: one card index per paper
        UniqueConstraint("paper_id", "card_index", name="uq_paper_card_index"),
        # Index for fetching all cards for a paper
        Index("ix_flashcards_paper_id", "paper_id"),
        # Index for filtering by topic
        Index("ix_flashcards_topic", "topic"),
        # Index for fetching fresh cards
        Index("ix_flashcards_generated_at", "generated_at"),
    )

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to papers table
    paper_id = Column(
        UUID(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to parent paper",
    )

    # Flashcard content (Q&A format)
    front = Column(Text, nullable=False, comment="Question, term, or concept")
    back = Column(Text, nullable=False, comment="Answer, definition, or explanation")

    # Organization
    topic = Column(String(100), nullable=True, comment="Topic/section (e.g., Architecture, Methods, Results)")
    difficulty = Column(String(20), nullable=True, comment="Difficulty: easy, medium, hard")
    card_index = Column(Integer, nullable=False, comment="Order within paper (0-indexed)")

    # Metadata
    generated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When this card was generated",
    )

    def __repr__(self):
        return f"<Flashcard(id={self.id}, paper_id={self.paper_id}, front='{self.front[:50]}...')>"


class FlashcardSetMetadata(Base):
    """
    Metadata for flashcard sets (one row per paper).

    Tracks generation timestamp and expiry for the entire set.
    """

    __tablename__ = "flashcard_set_metadata"

    # Primary key = paper_id (one metadata row per paper)
    paper_id = Column(
        UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True, comment="Reference to parent paper"
    )

    # Paper denormalized data (for quick access)
    arxiv_id = Column(String(50), nullable=True, comment="ArXiv ID (cached from papers table)")
    paper_title = Column(Text, nullable=False, comment="Paper title (cached from papers table)")

    # Set metadata
    total_cards = Column(Integer, nullable=False, comment="Total number of flashcards in this set")
    model_used = Column(String(100), nullable=False, comment="LLM model used for generation")

    # Staleness tracking
    generated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When flashcard set was generated",
    )
    expires_at = Column(DateTime(timezone=True), nullable=False, comment="When flashcard set becomes stale")

    def __repr__(self):
        return f"<FlashcardSetMetadata(paper_id={self.paper_id}, total_cards={self.total_cards})>"
