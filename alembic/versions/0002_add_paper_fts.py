"""
Add full text search support to papers
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# --- Alembic identifiers ---
revision = "0002_add_paper_fts"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None



def upgrade():
    # --- Add search vector column ---
    op.add_column(
        "papers",
        sa.Column("search_vector", postgresql.TSVECTOR),
    )

    # --- Trigger function ---
    op.execute("""
    CREATE FUNCTION papers_search_vector_update() RETURNS trigger AS $$
    BEGIN
      NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.abstract, '')), 'B');
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # --- Trigger ---
    op.execute("""
    CREATE TRIGGER tsvectorupdate
    BEFORE INSERT OR UPDATE ON papers
    FOR EACH ROW EXECUTE FUNCTION papers_search_vector_update();
    """)

    # --- Indexes ---
    op.create_index(
        "ix_papers_search_vector",
        "papers",
        ["search_vector"],
        postgresql_using="gin",
    )

    op.create_index(
        "ix_papers_categories",
        "papers",
        ["categories"],
        postgresql_using="gin",
    )

    # --- Backfill existing rows ---
    op.execute("""
    UPDATE papers
    SET search_vector =
      setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
      setweight(to_tsvector('english', coalesce(abstract, '')), 'B');
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS tsvectorupdate ON papers;")
    op.execute("DROP FUNCTION IF EXISTS papers_search_vector_update;")

    op.drop_index("ix_papers_search_vector", table_name="papers")
    op.drop_index("ix_papers_published_date", table_name="papers")
    op.drop_index("ix_papers_pdf_processed", table_name="papers")
    op.drop_index("ix_papers_categories", table_name="papers")

    op.drop_column("papers", "search_vector")
