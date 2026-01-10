"""
Initial schema: create papers table
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# --- Alembic identifiers ---
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "papers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("arxiv_id", sa.String(), nullable=False, unique=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("authors", postgresql.JSONB(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("categories", postgresql.JSONB(), nullable=False),
        sa.Column("published_date", sa.DateTime(), nullable=False),
        sa.Column("pdf_url", sa.String(), nullable=False),

        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("sections", postgresql.JSONB(), nullable=True),
        sa.Column("references", postgresql.JSONB(), nullable=True),

        sa.Column("parser_used", sa.String(), nullable=True),
        sa.Column("parser_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("pdf_processed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pdf_processing_date", sa.DateTime(), nullable=True),

        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
    )

    # baseline indexes
    op.create_index("ix_papers_arxiv_id", "papers", ["arxiv_id"])
    op.create_index("ix_papers_published_date", "papers", ["published_date"])


def downgrade():
    op.drop_index("ix_papers_published_date", table_name="papers")
    op.drop_index("ix_papers_arxiv_id", table_name="papers")
    op.drop_table("papers")
