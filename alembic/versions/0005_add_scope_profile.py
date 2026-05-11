"""
Add scope profiles and paper filter decisions

Creates two tables:
  scope_profiles          — versioned user-defined research scope that drives
                            the personalised ingestion filter pipeline
  paper_filter_decisions  — one row per paper per pipeline run, recording
                            every signal value and the final ingest/reject
                            decision for auditability and threshold tuning

Design notes:
  - scope_profiles.scope_vector is JSONB (list of floats). A single vector
    per profile does not warrant a pgvector extension — it is compared via
    Python at filter time, not via ANN search.
  - paper_filter_decisions.paper_id → papers.id with CASCADE so cleanup
    is automatic when a paper is deleted.
  - paper_filter_decisions.scope_profile_id uses SET NULL (not CASCADE) so
    that historical decisions are preserved for audit even when a profile
    is deleted.
  - UNIQUE(paper_id, scope_version_hash) prevents duplicate decisions for
    the same paper under the same scope version, while allowing re-evaluation
    when the scope changes (new version_hash → new row allowed).
  - All FK relationships use explicit constraint names for clean downgrade.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_add_scope_profile"
down_revision = "0004_add_projects"
branch_labels = None
depends_on = None


def upgrade():
    # =========================================================================
    # Table: scope_profiles
    # =========================================================================

    op.create_table(
        "scope_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        # Lexical filter
        sa.Column(
            "seed_paper_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="List of arXiv IDs used as positive examples",
        ),
        sa.Column(
            "required_terms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "excluded_terms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "lexical_match_mode",
            sa.String(3),
            nullable=False,
            server_default="any",
            comment="'any' or 'all'",
        ),
        # Scoring configuration
        sa.Column(
            "scoring_weights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("""'{"relevance": 0.70, "venue": 0.15, "citation": 0.15}'::jsonb"""),
        ),
        sa.Column(
            "thresholds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("""'{"embedding_high": 0.82, "embedding_low": 0.60, "composite_ingest": 0.72}'::jsonb"""),
        ),
        sa.Column(
            "journal_filter",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(
                """'{"enabled": false, "mode": "boost", "venues": [], "boost_factor": 0.10, "fallback_on_unknown": true}'::jsonb"""
            ),
        ),
        # Precomputed embedding centroid — NULL until first computed
        sa.Column(
            "scope_vector",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Embedding centroid of description + seed abstracts",
        ),
        sa.Column(
            "scope_vector_computed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        # Version tracking
        sa.Column(
            "version_hash",
            sa.String(64),
            nullable=False,
            comment="SHA-256 of content-bearing fields — changes when filtering behaviour changes",
        ),
        # Pipeline state
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
    )

    op.create_index("ix_scope_profiles_is_active", "scope_profiles", ["is_active"])
    op.create_index("ix_scope_profiles_created_at", "scope_profiles", ["created_at"])
    op.create_index("ix_scope_profiles_version_hash", "scope_profiles", ["version_hash"])

    # =========================================================================
    # Table: paper_filter_decisions
    # =========================================================================

    op.create_table(
        "paper_filter_decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Foreign keys
        sa.Column(
            "paper_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("papers.id", ondelete="CASCADE", name="fk_filter_decision_paper"),
            nullable=False,
        ),
        sa.Column(
            "scope_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "scope_profiles.id",
                ondelete="SET NULL",
                name="fk_filter_decision_scope_profile",
            ),
            nullable=True,
        ),
        sa.Column(
            "scope_version_hash",
            sa.String(64),
            nullable=False,
            comment="Profile version hash at decision time",
        ),
        # Layer 1 — Lexical
        sa.Column("lexical_passed", sa.Boolean(), nullable=False),
        # Layer 2 — Embedding
        sa.Column("embedding_score", sa.Float(), nullable=True),
        # Layer 3 — LLM reranker (NULL if not invoked)
        sa.Column("llm_relevant", sa.Boolean(), nullable=True),
        sa.Column("llm_confidence", sa.Float(), nullable=True),
        sa.Column("llm_reason", sa.Text(), nullable=True),
        # Semantic Scholar enrichment (NULL until enabled)
        sa.Column("venue", sa.String(255), nullable=True),
        sa.Column(
            "venue_type",
            sa.String(20),
            nullable=True,
            comment="'journal', 'conference', or 'preprint'",
        ),
        sa.Column(
            "venue_boost_applied",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column("citation_count", sa.Integer(), nullable=True),
        sa.Column("influential_citation_count", sa.Integer(), nullable=True),
        sa.Column(
            "citation_score",
            sa.Float(),
            nullable=True,
            comment="Age-normalised citation score, 0.0-1.0",
        ),
        # Final composite score and decision
        sa.Column("composite_score", sa.Float(), nullable=True),
        sa.Column(
            "decision",
            sa.String(10),
            nullable=False,
            comment="'ingested', 'rejected', or 'pending'",
        ),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
        # Table-level constraints
        sa.UniqueConstraint(
            "paper_id",
            "scope_version_hash",
            name="uq_filter_decision_paper_scope_version",
        ),
        sa.CheckConstraint(
            "decision IN ('ingested', 'rejected', 'pending')",
            name="check_valid_decision",
        ),
        sa.CheckConstraint(
            "(llm_relevant IS NULL) = (llm_confidence IS NULL)",
            name="check_llm_fields_consistent",
        ),
    )

    # Indexes on paper_filter_decisions
    op.create_index(
        "ix_filter_decisions_paper_id",
        "paper_filter_decisions",
        ["paper_id"],
    )
    op.create_index(
        "ix_filter_decisions_scope_profile_id",
        "paper_filter_decisions",
        ["scope_profile_id"],
    )
    op.create_index(
        "ix_filter_decisions_scope_version_hash",
        "paper_filter_decisions",
        ["scope_version_hash"],
    )
    op.create_index(
        "ix_filter_decisions_decision_decided_at",
        "paper_filter_decisions",
        ["decision", "decided_at"],
    )


def downgrade():
    # paper_filter_decisions
    op.drop_index("ix_filter_decisions_decision_decided_at", table_name="paper_filter_decisions")
    op.drop_index("ix_filter_decisions_scope_version_hash", table_name="paper_filter_decisions")
    op.drop_index("ix_filter_decisions_scope_profile_id", table_name="paper_filter_decisions")
    op.drop_index("ix_filter_decisions_paper_id", table_name="paper_filter_decisions")
    op.drop_table("paper_filter_decisions")

    # scope_profiles
    op.drop_index("ix_scope_profiles_version_hash", table_name="scope_profiles")
    op.drop_index("ix_scope_profiles_created_at", table_name="scope_profiles")
    op.drop_index("ix_scope_profiles_is_active", table_name="scope_profiles")
    op.drop_table("scope_profiles")
