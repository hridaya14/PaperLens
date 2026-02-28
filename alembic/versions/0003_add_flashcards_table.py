"""
Add flashcards table to cache summarized cards per category.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# --- Alembic identifiers ---
revision = "0003_add_flashcards_table"
down_revision = "0002_add_paper_fts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "flashcards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("category", sa.String(length=32), nullable=False, index=True),
        sa.Column("arxiv_id", sa.String(length=32), nullable=False),
        sa.Column("headline", sa.String(length=512), nullable=False),
        sa.Column("insight", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), onupdate=sa.text("timezone('utc', now())")),
        sa.UniqueConstraint("category", "arxiv_id", name="uq_flashcards_category_arxiv_id"),
    )

    op.create_index(
        "ix_flashcards_category_expires",
        "flashcards",
        ["category", "expires_at"],
    )

    op.create_index(
        "ix_flashcards_expires_at",
        "flashcards",
        ["expires_at"],
    )


def downgrade():
    op.drop_index("ix_flashcards_expires_at", table_name="flashcards")
    op.drop_index("ix_flashcards_category_expires", table_name="flashcards")
    op.drop_table("flashcards")
