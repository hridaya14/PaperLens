"""
Pydantic schemas for flashcards feature (NotebookLM-style).

Multiple flashcards per paper, each covering a specific concept/topic.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# Core Flashcard Models
# ============================================================================


class FlashcardContent(BaseModel):
    """Individual flashcard content (Q&A or Front/Back format)."""

    front: str = Field(..., description="Question, term, or concept", min_length=5, max_length=500)
    back: str = Field(..., description="Answer, definition, or explanation", min_length=10, max_length=2000)

    # Optional metadata
    topic: Optional[str] = Field(
        None, description="Topic/section this card belongs to (e.g., 'Architecture', 'Methods')", max_length=100
    )
    difficulty: Optional[str] = Field(None, description="Difficulty level: easy, medium, hard", pattern="^(easy|medium|hard)$")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "front": "What is the main innovation of the Transformer architecture?",
                "back": "Self-attention mechanism that allows parallel processing of sequences, replacing sequential RNN computation",
                "topic": "Architecture",
                "difficulty": "medium",
            }
        }
    )


class Flashcard(BaseModel):
    """Single flashcard belonging to a paper."""

    # Identifiers
    id: Optional[int] = Field(None, description="Database primary key")
    paper_id: str = Field(..., description="UUID of the parent paper")

    # Content
    front: str
    back: str
    topic: Optional[str] = None
    difficulty: Optional[str] = None

    # Ordering/grouping
    card_index: int = Field(..., description="Order of this card within the paper (0-indexed)", ge=0)

    # Metadata
    generated_at: datetime = Field(..., description="When card was generated")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 123,
                "paper_id": "550e8400-e29b-41d4-a716-446655440000",
                "front": "What problem does the Transformer architecture solve?",
                "back": "Sequential processing bottleneck in RNNs that prevents parallelization",
                "topic": "Motivation",
                "difficulty": "easy",
                "card_index": 0,
                "generated_at": "2024-01-15T10:30:00Z",
            }
        }
    )


class FlashcardSet(BaseModel):
    """Complete set of flashcards for a paper."""

    # Paper identification
    paper_id: str
    arxiv_id: Optional[str] = None
    paper_title: str

    # Flashcards
    flashcards: List[Flashcard] = Field(..., description="List of flashcards for this paper")

    # Metadata
    total_cards: int = Field(..., description="Total number of flashcards")
    generated_at: datetime = Field(..., description="When set was generated")
    expires_at: datetime = Field(..., description="When flashcards become stale")
    model_used: str = Field(..., description="LLM model used")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "paper_id": "550e8400-e29b-41d4-a716-446655440000",
                "arxiv_id": "2401.12345",
                "paper_title": "Attention Is All You Need",
                "flashcards": [
                    {
                        "id": 1,
                        "paper_id": "550e8400-e29b-41d4-a716-446655440000",
                        "front": "What is self-attention?",
                        "back": "A mechanism that computes attention weights...",
                        "topic": "Core Concepts",
                        "card_index": 0,
                        "generated_at": "2024-01-15T10:30:00Z",
                    }
                ],
                "total_cards": 15,
                "generated_at": "2024-01-15T10:30:00Z",
                "expires_at": "2024-01-22T10:30:00Z",
                "model_used": "meta/llama-3.3-70b-instruct",
            }
        }
    )


# ============================================================================
# API Request/Response Models
# ============================================================================


class FlashcardGenerateRequest(BaseModel):
    """Request to generate flashcards for a paper."""

    paper_id: str = Field(..., description="UUID of paper to generate flashcards for")
    num_cards: int = Field(default=15, ge=5, le=50, description="Number of flashcards to generate")
    force_refresh: bool = Field(default=False, description="Regenerate even if fresh flashcards exist")
    topics: Optional[List[str]] = Field(None, description="Specific topics to focus on (e.g., ['Methods', 'Results'])")


class FlashcardResponse(BaseModel):
    """Single flashcard response for API."""

    id: Optional[int] = None
    paper_id: str
    front: str
    back: str
    topic: Optional[str]
    difficulty: Optional[str]
    card_index: int
    generated_at: datetime

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 123,
                "paper_id": "550e8400-e29b-41d4-a716-446655440000",
                "front": "What is the Transformer's time complexity?",
                "back": "O(n²·d) where n is sequence length and d is dimension",
                "topic": "Complexity",
                "difficulty": "hard",
                "card_index": 5,
                "generated_at": "2024-01-15T10:30:00Z",
            }
        }
    )


class FlashcardSetResponse(BaseModel):
    """Response containing all flashcards for a paper."""

    paper_id: str
    arxiv_id: Optional[str]
    paper_title: str
    flashcards: List[FlashcardResponse]

    meta: dict = Field(default_factory=dict, description="Metadata about the flashcard set")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "paper_id": "550e8400-e29b-41d4-a716-446655440000",
                "arxiv_id": "2401.12345",
                "paper_title": "Attention Is All You Need",
                "flashcards": [
                    {
                        "id": 1,
                        "paper_id": "550e8400-e29b-41d4-a716-446655440000",
                        "front": "What is self-attention?",
                        "back": "...",
                        "topic": "Core Concepts",
                        "card_index": 0,
                        "generated_at": "2024-01-15T10:30:00Z",
                    }
                ],
                "meta": {
                    "total_cards": 15,
                    "generated_at": "2024-01-15T10:30:00Z",
                    "is_fresh": True,
                    "topics_covered": ["Architecture", "Methods", "Results"],
                },
            }
        }
    )


# ============================================================================
# Database Models
# ============================================================================


class FlashcardCreate(BaseModel):
    """Schema for creating a flashcard in DB."""

    paper_id: str
    front: str
    back: str
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    card_index: int
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FlashcardSetCreate(BaseModel):
    """Schema for creating a complete flashcard set."""

    paper_id: str
    arxiv_id: Optional[str] = None
    paper_title: str
    flashcards: List[FlashcardCreate]
    generated_at: datetime
    expires_at: datetime
    model_used: str

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# LLM Generation Models
# ============================================================================


class FlashcardGenerationInput(BaseModel):
    """Input to LLM for flashcard generation."""

    paper_title: str
    paper_abstract: str
    paper_content: str  # Full text or key sections
    num_cards: int = 15
    topics: Optional[List[str]] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "paper_title": "Attention Is All You Need",
                "paper_abstract": "The dominant sequence transduction models...",
                "paper_content": "# Introduction\n\nRecurrent neural networks...",
                "num_cards": 15,
                "topics": ["Architecture", "Training", "Results"],
            }
        }
    )


class FlashcardGenerationOutput(BaseModel):
    """Output from LLM flashcard generation."""

    flashcards: List[FlashcardContent] = Field(..., description="Generated flashcards")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "flashcards": [
                    {
                        "front": "What is self-attention?",
                        "back": "A mechanism that...",
                        "topic": "Architecture",
                        "difficulty": "medium",
                    },
                    {
                        "front": "Why did the authors propose Transformers?",
                        "back": "To overcome sequential processing limitations...",
                        "topic": "Motivation",
                        "difficulty": "easy",
                    },
                ]
            }
        }
    )


# ============================================================================
# Cache Models (Redis)
# ============================================================================


class FlashcardSetCacheEntry(BaseModel):
    """Wrapper for flashcard set stored in Redis."""

    flashcard_set: FlashcardSet
    cache_version: int
    hit_count: int = 0
    cached_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FlashcardCacheStatus(BaseModel):
    """Status of flashcard set in cache."""

    paper_id: str
    is_cached: bool
    num_cards: Optional[int] = None
    cached_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    ttl_seconds: Optional[int] = None
