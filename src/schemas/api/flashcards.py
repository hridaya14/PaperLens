from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class FlashcardDTO(BaseModel):
    """Serialized flashcard returned by the API/UI."""

    category: str = Field(..., description="arXiv category code, e.g., cs.AI")
    arxiv_id: str = Field(..., description="arXiv identifier for the source paper")
    headline: str = Field(..., description="Short headline summarizing the paper")
    insight: str = Field(..., description="Key finding or takeaway")
    why_it_matters: Optional[str] = Field(
        None, description="Optional context on impact or relevance"
    )
    generated_at: datetime = Field(
        ..., description="Timestamp when this flashcard was generated"
    )
    expires_at: datetime = Field(
        ..., description="Timestamp after which the card is considered stale"
    )
    source_url: Optional[str] = Field(
        None, description="Direct PDF/abstract URL for the source paper"
    )


class FlashcardsResponse(BaseModel):
    """Response envelope for a set of flashcards."""

    category: str
    cards: List[FlashcardDTO]
    stale: bool = Field(
        False,
        description="True if the cards are past expires_at at response time",
    )
    regenerated: bool = Field(
        False,
        description="True if generation was triggered for this response",
    )


class FlashcardsQuery(BaseModel):
    """Query parameters for fetching flashcards."""

    category: str = Field(..., description="arXiv category code, e.g., cs.AI")
    limit: int = Field(5, ge=1, le=10, description="Number of cards to return")
    refresh: bool = Field(
        False,
        description="Force regeneration even if fresh cards exist",
    )
