"""
Pydantic schemas for the scope profile system.

A ScopeProfile captures a user's research interests and drives all filtering
decisions in the ingestion pipeline. It is a versioned entity — every change
produces a new version_hash so that historical filter decisions can be traced
back to the exact profile state that produced them.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Sub-schemas (embedded in ScopeProfile as JSONB columns)
# ---------------------------------------------------------------------------


class ScoringWeights(BaseModel):
    """Relative importance of each signal in the composite score.

    Must sum to 1.0. When citation data is unavailable the citation weight
    is redistributed to relevance automatically at scoring time.
    """

    relevance: float = Field(0.70, ge=0.0, le=1.0)
    venue: float = Field(0.15, ge=0.0, le=1.0)
    citation: float = Field(0.15, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "ScoringWeights":
        total = round(self.relevance + self.venue + self.citation, 6)
        if abs(total - 1.0) > 1e-4:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}. Adjust relevance, venue, or citation.")
        return self


class FilteringThresholds(BaseModel):
    """Thresholds that control which layer makes the ingestion decision.

    The embedding score defines three zones:
      score >= high  →  fast-track ingest  (skip LLM)
      score <= low   →  fast-track reject  (skip LLM)
      low < score < high  →  send to LLM reranker

    The composite threshold is the final gate applied after all signals
    are combined.
    """

    embedding_high: float = Field(
        0.82,
        ge=0.0,
        le=1.0,
        description="Above this → ingest without LLM reranking",
    )
    embedding_low: float = Field(
        0.60,
        ge=0.0,
        le=1.0,
        description="Below this → reject without LLM reranking",
    )
    composite_ingest: float = Field(
        0.72,
        ge=0.0,
        le=1.0,
        description="Composite score must exceed this to ingest",
    )

    @model_validator(mode="after")
    def low_below_high(self) -> "FilteringThresholds":
        if self.embedding_low >= self.embedding_high:
            raise ValueError(
                f"embedding_low ({self.embedding_low}) must be strictly less than embedding_high ({self.embedding_high})"
            )
        return self


class JournalFilterConfig(BaseModel):
    """Configuration for the venue/journal soft signal."""

    enabled: bool = False
    # "boost"   — matching venue increases composite score
    # "require" — papers without a matching venue are rejected
    # "exclude" — papers from listed venues are rejected
    mode: str = Field("boost", pattern="^(boost|require|exclude)$")
    venues: List[str] = Field(
        default_factory=list,
        description="Venue names to match against (case-insensitive substring match)",
    )
    boost_factor: float = Field(
        0.10,
        ge=0.0,
        le=1.0,
        description="Score added when venue matches (mode=boost only)",
    )
    # When True, papers with no venue information are NOT rejected
    # even when mode="require" — they are treated as "unverified"
    fallback_on_unknown: bool = True


# ---------------------------------------------------------------------------
# Core schemas
# ---------------------------------------------------------------------------


class ScopeProfileBase(BaseModel):
    """Fields shared across create / update / response."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(
        ...,
        min_length=10,
        description=(
            "Free-text description of your research interests. This is embedded to form the scope vector — be specific."
        ),
    )
    # Seed papers: their abstracts are embedded and averaged into the
    # scope vector alongside the description.
    seed_paper_ids: List[str] = Field(
        default_factory=list,
        description="arXiv IDs of papers you already consider relevant",
    )
    required_terms: List[str] = Field(
        default_factory=list,
        description="At least one (or all, per match_mode) must appear in title+abstract",
    )
    excluded_terms: List[str] = Field(
        default_factory=list,
        description="Papers containing any of these terms are always rejected",
    )
    # "any" | "all"
    lexical_match_mode: str = Field(
        "any",
        pattern="^(any|all)$",
        description="Whether 'any' or 'all' required_terms must match",
    )
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    thresholds: FilteringThresholds = Field(default_factory=FilteringThresholds)
    journal_filter: JournalFilterConfig = Field(default_factory=JournalFilterConfig)
    is_active: bool = Field(
        True,
        description="Only one profile should be active at a time in the pipeline",
    )

    @field_validator("seed_paper_ids")
    @classmethod
    def validate_arxiv_ids(cls, ids: List[str]) -> List[str]:
        """Basic sanity check — arXiv IDs should not be empty strings."""
        cleaned = [i.strip() for i in ids if i.strip()]
        return cleaned


class ScopeProfileCreate(ScopeProfileBase):
    """Schema for creating a new scope profile via the API."""

    pass


class ScopeProfileUpdate(BaseModel):
    """Schema for partial updates — all fields optional."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=10)
    seed_paper_ids: Optional[List[str]] = None
    required_terms: Optional[List[str]] = None
    excluded_terms: Optional[List[str]] = None
    lexical_match_mode: Optional[str] = Field(None, pattern="^(any|all)$")
    scoring_weights: Optional[ScoringWeights] = None
    thresholds: Optional[FilteringThresholds] = None
    journal_filter: Optional[JournalFilterConfig] = None
    is_active: Optional[bool] = None


class ScopeProfileResponse(ScopeProfileBase):
    """Schema for API responses — includes DB-generated fields."""

    id: UUID
    # SHA-256 of the profile's content-bearing fields.
    # Stored alongside every filter decision so decisions can be traced
    # back to the exact profile state that produced them.
    version_hash: str
    # The scope vector is NOT returned in API responses (it can be large
    # and is not human-readable). Presence flag instead.
    has_scope_vector: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Filter decision schemas
# ---------------------------------------------------------------------------


class FilterDecisionCreate(BaseModel):
    """Written to the DB once per paper per pipeline run."""

    paper_id: UUID
    scope_profile_id: UUID
    scope_version_hash: str

    # Layer 1
    lexical_passed: bool

    # Layer 2
    embedding_score: Optional[float] = None

    # Layer 3 (None if not invoked — paper was fast-tracked)
    llm_relevant: Optional[bool] = None
    llm_confidence: Optional[float] = None
    llm_reason: Optional[str] = None

    # Enrichment (None until Semantic Scholar is enabled)
    venue: Optional[str] = None
    venue_type: Optional[str] = None  # "journal" | "conference" | "preprint"
    venue_boost_applied: float = 0.0
    citation_count: Optional[int] = None
    influential_citation_count: Optional[int] = None
    citation_score: Optional[float] = None  # Normalised 0-1

    # Final result
    composite_score: Optional[float] = None
    decision: str = Field(..., pattern="^(ingested|rejected|pending)$")
    decided_at: datetime = Field(default_factory=datetime.utcnow)


class FilterDecisionResponse(FilterDecisionCreate):
    """API response shape for a filter decision record."""

    id: UUID

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Helper — version hash computation
# ---------------------------------------------------------------------------


def compute_scope_version_hash(profile: ScopeProfileBase) -> str:
    """
    Produce a stable SHA-256 hash of the content-bearing fields of a profile.

    Only fields that affect filtering behaviour are included — name and
    is_active are excluded because changing them should not invalidate
    historical decisions.
    """
    content: Dict[str, Any] = {
        "description": profile.description,
        "seed_paper_ids": sorted(profile.seed_paper_ids),
        "required_terms": sorted(profile.required_terms),
        "excluded_terms": sorted(profile.excluded_terms),
        "lexical_match_mode": profile.lexical_match_mode,
        "scoring_weights": profile.scoring_weights.model_dump(),
        "thresholds": profile.thresholds.model_dump(),
        "journal_filter": profile.journal_filter.model_dump(),
    }
    serialised = json.dumps(content, sort_keys=True, default=str)
    return hashlib.sha256(serialised.encode()).hexdigest()
