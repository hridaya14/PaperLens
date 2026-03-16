"""
Add user upload support and flashcard tables

This migration:
1. Adds user upload support to papers table
2. Creates flashcard tables (NotebookLM-style: multiple cards per paper)

Changes to papers table:
- Add source column (arxiv/user_upload)
- Add original_filename for uploads
- Add uploaded_at timestamp
- Make arxiv_id nullable (required for user uploads)
- Add check constraint for data integrity

New tables:
- flashcards: Individual Q&A flashcards
- flashcard_set_metadata: Metadata for flashcard sets per paper

Backwards compatibility:
- All existing papers get source='arxiv'
- Existing arxiv_id values preserved
- No data loss
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# --- Alembic identifiers ---
revision = "3d4f5a6b7c8e"
down_revision = "0002_add_paper_fts"
branch_labels = None
depends_on = None


def upgrade():
    """
    Add user upload support and create flashcard tables.
    """

    # =========================================================================
    # PART 1: User Upload Support for Papers Table
    # =========================================================================

    # --- Step 1: Add new columns with defaults ---

    # Source tracking (defaults to 'arxiv' for existing papers)
    op.add_column(
        "papers",
        sa.Column(
            "source", sa.String(20), nullable=False, server_default="arxiv", comment="Source of paper: arxiv or user_upload"
        ),
    )

    # Original filename (NULL for ArXiv papers)
    op.add_column(
        "papers",
        sa.Column("original_filename", sa.Text(), nullable=True, comment="Original filename for user uploads"),
    )

    # Upload timestamp (NULL for ArXiv papers)
    op.add_column(
        "papers",
        sa.Column("uploaded_at", sa.DateTime(), nullable=True, comment="Timestamp when paper was uploaded"),
    )

    # --- Step 2: Make arxiv_id nullable ---
    # This allows user uploads to have NULL arxiv_id
    # PostgreSQL UNIQUE constraint allows multiple NULL values, so this is safe
    op.alter_column(
        "papers",
        "arxiv_id",
        existing_type=sa.String(),
        nullable=True,
        existing_nullable=False,
        comment="ArXiv ID (e.g., 2401.12345), NULL for user uploads",
    )

    # --- Step 3: Backfill existing rows ---
    # Ensure all existing papers have source='arxiv'
    op.execute("""
        UPDATE papers
        SET source = 'arxiv'
        WHERE source IS NULL;
    """)

    # --- Step 4: Add check constraint ---
    # Ensure arxiv papers have arxiv_id
    op.create_check_constraint("check_arxiv_has_id", "papers", "source != 'arxiv' OR arxiv_id IS NOT NULL")

    # --- Step 5: Add indexes for efficient queries ---

    # Index for filtering by source
    op.create_index("ix_papers_source", "papers", ["source"])

    # --- Step 6: Remove server default (only needed for migration) ---
    # After backfill, we rely on application-level defaults
    op.alter_column("papers", "source", server_default=None)

    # =========================================================================
    # PART 2: Flashcard Tables
    # =========================================================================

    # -------------------------------------------------------------------------
    # Table 1: flashcards (individual Q&A cards)
    # -------------------------------------------------------------------------

    op.create_table(
        "flashcards",
        # Primary key
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        # Foreign key to papers
        sa.Column(
            "paper_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            nullable=False,
            comment="Reference to parent paper",
        ),
        # Content (Q&A format)
        sa.Column("front", sa.Text(), nullable=False, comment="Question, term, or concept"),
        sa.Column("back", sa.Text(), nullable=False, comment="Answer, definition, or explanation"),
        # Organization
        sa.Column("topic", sa.String(100), nullable=True, comment="Topic/section (e.g., Architecture, Methods)"),
        sa.Column("difficulty", sa.String(20), nullable=True, comment="Difficulty: easy, medium, hard"),
        sa.Column("card_index", sa.Integer(), nullable=False, comment="Order within paper (0-indexed)"),
        # Metadata
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
            comment="When this card was generated",
        ),
    )

    # --- Indexes for flashcards table ---

    # Index for fetching all cards for a paper (most common query)
    op.create_index("ix_flashcards_paper_id", "flashcards", ["paper_id"])

    # Index for filtering by topic
    op.create_index("ix_flashcards_topic", "flashcards", ["topic"])

    # Index for chronological ordering
    op.create_index("ix_flashcards_generated_at", "flashcards", ["generated_at"])

    # Composite index for fetching cards in order
    op.create_index("ix_flashcards_paper_card_index", "flashcards", ["paper_id", "card_index"])

    # --- Unique constraint ---
    # Ensure each paper has unique card indices
    op.create_unique_constraint("uq_paper_card_index", "flashcards", ["paper_id", "card_index"])

    # -------------------------------------------------------------------------
    # Table 2: flashcard_set_metadata (one row per paper)
    # -------------------------------------------------------------------------

    op.create_table(
        "flashcard_set_metadata",
        # Primary key = paper_id (one metadata row per paper)
        sa.Column(
            "paper_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            primary_key=True,
            comment="Reference to parent paper",
        ),
        # Cached paper data (denormalized for quick access)
        sa.Column("arxiv_id", sa.String(50), nullable=True, comment="ArXiv ID (cached from papers table)"),
        sa.Column("paper_title", sa.Text(), nullable=False, comment="Paper title (cached from papers table)"),
        # Set metadata
        sa.Column("total_cards", sa.Integer(), nullable=False, comment="Total number of flashcards in this set"),
        sa.Column("model_used", sa.String(100), nullable=False, comment="LLM model used for generation"),
        # Staleness tracking
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
            comment="When flashcard set was generated",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, comment="When flashcard set becomes stale"),
    )

    # --- Indexes for flashcard_set_metadata table ---

    # Index for finding stale sets (cleanup queries)
    op.create_index("ix_flashcard_set_metadata_expires_at", "flashcard_set_metadata", ["expires_at"])

    # Index for chronological listing
    op.create_index("ix_flashcard_set_metadata_generated_at", "flashcard_set_metadata", ["generated_at"])


def downgrade():
    """
    Revert all changes.

    WARNING: This will:
    - Delete all user upload papers
    - Delete all flashcard data
    """

    # =========================================================================
    # PART 1: Drop Flashcard Tables
    # =========================================================================

    # Drop indexes for flashcard_set_metadata
    op.drop_index("ix_flashcard_set_metadata_generated_at", table_name="flashcard_set_metadata")
    op.drop_index("ix_flashcard_set_metadata_expires_at", table_name="flashcard_set_metadata")

    # Drop indexes for flashcards
    op.drop_index("ix_flashcards_paper_card_index", table_name="flashcards")
    op.drop_index("ix_flashcards_generated_at", table_name="flashcards")
    op.drop_index("ix_flashcards_topic", table_name="flashcards")
    op.drop_index("ix_flashcards_paper_id", table_name="flashcards")

    # Drop unique constraint
    op.drop_constraint("uq_paper_card_index", "flashcards", type_="unique")

    # Drop tables
    op.drop_table("flashcard_set_metadata")
    op.drop_table("flashcards")

    # =========================================================================
    # PART 2: Revert User Upload Support
    # =========================================================================

    # Drop index
    op.drop_index("ix_papers_source", table_name="papers")

    # Drop check constraint
    op.drop_constraint("check_arxiv_has_id", "papers", type_="check")

    # Make arxiv_id NOT NULL again (will fail if user uploads exist)
    op.alter_column("papers", "arxiv_id", existing_type=sa.String(), nullable=False)

    # Drop new columns
    op.drop_column("papers", "uploaded_at")
    op.drop_column("papers", "original_filename")
    op.drop_column("papers", "source")
