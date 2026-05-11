"""
SQLAlchemy models for the scope profile system.

Two tables:
  scope_profiles          — versioned user-defined research scope
  paper_filter_decisions  — one row per paper per pipeline run, recording
                            every signal and the final ingest/reject decision
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from src.db.interfaces.postgresql import Base


def _utcnow():
    return datetime.now(timezone.utc)


class ScopeProfile(Base):
    """
    A versioned research scope profile that drives the ingestion filter pipeline.

    Design notes:
    - scope_vector stores the precomputed embedding centroid (list of floats)
      as JSONB. This is intentionally not stored in OpenSearch — it is a
      single vector used only for dot-product comparison, not for ANN search.
    - version_hash is recomputed and persisted on every save so historical
      filter decisions can be traced back to the exact profile state.
    - Only one profile should have is_active=True at a time. This is enforced
      at the repository layer, not via a DB constraint, to allow atomic swaps.
    """

    __tablename__ = "scope_profiles"

    __table_args__ = (
        Index("ix_scope_profiles_is_active", "is_active"),
        Index("ix_scope_profiles_created_at", "created_at"),
    )

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Human-readable identifier
    name = Column(String(255), nullable=False)

    # Free-text research scope description — this is what gets embedded
    description = Column(Text, nullable=False)

    # arXiv IDs of seed papers (their abstracts contribute to scope_vector)
    seed_paper_ids = Column(
        JSONB,
        nullable=False,
        default=list,
        comment="List of arXiv IDs used as positive examples",
    )

    # Lexical filter config
    required_terms = Column(JSONB, nullable=False, default=list)
    excluded_terms = Column(JSONB, nullable=False, default=list)
    lexical_match_mode = Column(
        String(3),
        nullable=False,
        default="any",
        comment="'any' or 'all' — how required_terms are matched",
    )

    # Scoring configuration (stored as JSONB dicts matching Pydantic sub-schemas)
    scoring_weights = Column(
        JSONB,
        nullable=False,
        default=lambda: {"relevance": 0.70, "venue": 0.15, "citation": 0.15},
        comment="Weights for relevance, venue, citation signals",
    )
    thresholds = Column(
        JSONB,
        nullable=False,
        default=lambda: {
            "embedding_high": 0.82,
            "embedding_low": 0.60,
            "composite_ingest": 0.72,
        },
        comment="Embedding fast-track thresholds and composite ingest gate",
    )
    journal_filter = Column(
        JSONB,
        nullable=False,
        default=lambda: {
            "enabled": False,
            "mode": "boost",
            "venues": [],
            "boost_factor": 0.10,
            "fallback_on_unknown": True,
        },
        comment="Journal/venue filter configuration",
    )

    # Precomputed embedding centroid of description + seed paper abstracts.
    # List[float] stored as JSONB. NULL until first computed.
    scope_vector = Column(
        JSONB,
        nullable=True,
        comment="Precomputed embedding centroid — recomputed when profile changes",
    )
    scope_vector_computed_at = Column(DateTime(timezone=True), nullable=True)

    # SHA-256 of content-bearing fields — changes whenever filtering behaviour
    # would change. Stored on every filter decision for traceability.
    version_hash = Column(String(64), nullable=False, index=True)

    # Pipeline state
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this profile is used by the ingestion pipeline",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<ScopeProfile(id={self.id}, name='{self.name}', active={self.is_active}, version={self.version_hash[:8]}...)>"

    @property
    def has_scope_vector(self) -> bool:
        return self.scope_vector is not None


class PaperFilterDecision(Base):
    """
    One row per paper per pipeline run.

    Records every signal value and the final ingest/reject decision so that:
    - Filter quality can be audited over time
    - Thresholds can be tuned against historical data
    - Previously rejected papers can be re-evaluated when the scope changes
      (scope_version_hash changes → old decisions remain, new ones are added)

    Design notes:
    - paper_id → papers.id with CASCADE so cleanup is automatic
    - scope_profile_id → scope_profiles.id with SET NULL so decisions are
      preserved even if a profile is deleted (for historical audit)
    - UNIQUE(paper_id, scope_version_hash) prevents duplicate decisions for
      the same paper under the same scope version
    """

    __tablename__ = "paper_filter_decisions"

    __table_args__ = (
        # Prevent duplicate decisions for same paper + scope version
        UniqueConstraint(
            "paper_id",
            "scope_version_hash",
            name="uq_filter_decision_paper_scope_version",
        ),
        # Fast lookup: "show me all decisions for this run"
        Index("ix_filter_decisions_scope_profile_id", "scope_profile_id"),
        # Fast lookup: "what was decided for this paper?"
        Index("ix_filter_decisions_paper_id", "paper_id"),
        # Useful for auditing rejection rates over time
        Index("ix_filter_decisions_decision_decided_at", "decision", "decided_at"),
        # Constraint: decision must be a known value
        CheckConstraint(
            "decision IN ('ingested', 'rejected', 'pending')",
            name="check_valid_decision",
        ),
        # Constraint: llm fields must be consistent
        CheckConstraint(
            "(llm_relevant IS NULL) = (llm_confidence IS NULL)",
            name="check_llm_fields_consistent",
        ),
    )

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    paper_id = Column(
        UUID(as_uuid=True),
        # Inline FK — same pattern as project_sources in 0004 migration
        nullable=False,
        comment="References papers.id",
    )
    scope_profile_id = Column(
        UUID(as_uuid=True),
        nullable=True,  # SET NULL when profile deleted — preserve audit trail
        comment="References scope_profiles.id (nullable for audit preservation)",
    )

    # The version hash at decision time — decoupled from scope_profile_id so
    # that even if the profile is updated we know exactly what config decided
    scope_version_hash = Column(String(64), nullable=False)

    # -------------------------------------------------------------------------
    # Layer 1 — Lexical
    # -------------------------------------------------------------------------
    lexical_passed = Column(Boolean, nullable=False)

    # -------------------------------------------------------------------------
    # Layer 2 — Embedding similarity
    # -------------------------------------------------------------------------
    embedding_score = Column(Float, nullable=True)

    # -------------------------------------------------------------------------
    # Layer 3 — LLM reranker (NULL if not invoked)
    # -------------------------------------------------------------------------
    llm_relevant = Column(Boolean, nullable=True)
    llm_confidence = Column(Float, nullable=True)
    llm_reason = Column(Text, nullable=True)

    # -------------------------------------------------------------------------
    # Semantic Scholar enrichment (NULL until enabled)
    # -------------------------------------------------------------------------
    venue = Column(String(255), nullable=True)
    venue_type = Column(
        String(20),
        nullable=True,
        comment="'journal', 'conference', or 'preprint'",
    )
    venue_boost_applied = Column(Float, nullable=False, default=0.0)
    citation_count = Column(Integer, nullable=True)
    influential_citation_count = Column(Integer, nullable=True)
    # Age-normalised citation score (0.0–1.0 percentile within batch)
    citation_score = Column(Float, nullable=True)

    # -------------------------------------------------------------------------
    # Final composite score and decision
    # -------------------------------------------------------------------------
    composite_score = Column(Float, nullable=True)
    decision = Column(
        String(10),
        nullable=False,
        comment="'ingested', 'rejected', or 'pending'",
    )
    decided_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    def __repr__(self) -> str:
        return (
            f"<PaperFilterDecision("
            f"paper_id={self.paper_id}, "
            f"decision='{self.decision}', "
            f"composite={self.composite_score:.3f if self.composite_score else 'N/A'}"
            f")>"
        )

    @property
    def llm_was_invoked(self) -> bool:
        return self.llm_relevant is not None

    @property
    def fast_tracked(self) -> bool:
        """True if the embedding score alone determined the outcome."""
        return not self.llm_was_invoked
