from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from src.models.paper import Paper


class FlashcardRecord:
    """Lightweight typed record for flashcards table rows."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.category = kwargs.get("category")
        self.arxiv_id = kwargs.get("arxiv_id")
        self.headline = kwargs.get("headline")
        self.insight = kwargs.get("insight")
        self.why_it_matters = kwargs.get("why_it_matters")
        self.summary_json = kwargs.get("summary_json")
        self.generated_at = kwargs.get("generated_at")
        self.expires_at = kwargs.get("expires_at")
        self.created_at = kwargs.get("created_at")
        self.updated_at = kwargs.get("updated_at")


class FlashcardsRepository:
    """Data access layer for flashcards."""

    def __init__(self, session: Session):
        self.session = session
        self.table = self._flashcards_table()

    def _flashcards_table(self):
        # Late import to avoid declarative base coupling
        from sqlalchemy import Table, MetaData
        meta = MetaData()
        meta.reflect(bind=self.session.bind, only=["flashcards"])
        return Table("flashcards", meta, autoload_with=self.session.bind)

    def get_fresh(
        self, category: str, limit: int, now: Optional[datetime] = None
    ) -> List[FlashcardRecord]:
        now = now or datetime.now(timezone.utc)
        stmt = (
            select(self.table)
            .where(
                and_(
                    self.table.c.category == category,
                    self.table.c.generated_at.isnot(None),
                    self.table.c.expires_at.isnot(None),
                    self.table.c.expires_at > now,
                )
            )
            .order_by(self.table.c.generated_at.desc())
            .limit(limit)
        )
        rows = self.session.execute(stmt).fetchall()
        return [FlashcardRecord(**row._asdict()) for row in rows]

    def upsert_cards(self, records: List[dict]) -> None:
        """Simple upsert based on category+arxiv_id uniqueness."""
        if not records:
            return
        # Use ON CONFLICT for PostgreSQL
        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(self.table).values(records)
        update_cols = {
            "headline": stmt.excluded.headline,
            "insight": stmt.excluded.insight,
            "why_it_matters": stmt.excluded.why_it_matters,
            "summary_json": stmt.excluded.summary_json,
            "generated_at": stmt.excluded.generated_at,
            "expires_at": stmt.excluded.expires_at,
            "updated_at": datetime.now(timezone.utc),
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_flashcards_category_arxiv_id",
            set_=update_cols,
        )
        self.session.execute(stmt)
        self.session.commit()

    def delete_expired(self, limit: int = 500) -> int:
        """Best-effort cleanup of expired rows."""
        now = datetime.now(timezone.utc)
        stmt = (
            delete(self.table)
            .where(self.table.c.expires_at < now)
            .limit(limit)
            .returning(self.table.c.id)
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return result.rowcount or 0

    def get_recent_papers_for_category(
        self, category: str, max_candidates: int = 20
    ) -> List[Paper]:
        """Helper to fetch recent parsed papers for a category."""
        stmt = (
            select(Paper)
            .where(
                and_(
                    Paper.categories.contains([category]),
                    Paper.pdf_processed.is_(True),
                )
            )
            .order_by(Paper.published_date.desc())
            .limit(max_candidates)
        )
        return list(self.session.scalars(stmt))
