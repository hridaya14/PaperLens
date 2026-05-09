from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from src.models.paper import Paper
from src.schemas.arxiv.paper import PaperCreate, PaperSearchFilters


class PaperRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, paper: PaperCreate) -> Paper:
        db_paper = Paper(**paper.model_dump())
        self.session.add(db_paper)
        self.session.commit()
        self.session.refresh(db_paper)
        return db_paper

    def get_by_arxiv_id(self, arxiv_id: str) -> Optional[Paper]:
        stmt = select(Paper).where(Paper.arxiv_id == arxiv_id)
        return self.session.scalar(stmt)

    def get_by_id(self, paper_id: UUID) -> Optional[Paper]:
        stmt = select(Paper).where(Paper.id == paper_id)
        return self.session.scalar(stmt)

    def get_by_id_or_arxiv_id(self, paper_ref: str) -> Optional[Paper]:
        """Resolve a paper from either a UUID string or an arXiv ID string.

        Resolution order:
        1. Try to parse *paper_ref* as a UUID → look up by primary key.
        2. Fall back to arXiv ID lookup.

        This lets visualization endpoints accept both user-uploaded papers
        (identified by UUID) and arXiv-ingested papers (identified by arXiv ID)
        under the same ``paper_id`` path parameter.

        Args:
            paper_ref: Either a UUID string (e.g. ``"3fa85f64-5717-4562-b3fc-2c963f66afa6"``)
                       or an arXiv ID string (e.g. ``"2401.00001"`` / ``"2401.00001v2"``).

        Returns:
            The matching :class:`Paper` ORM instance, or ``None`` if not found.
        """
        # 1. Try UUID path first — UUIDs always contain hyphens in the canonical
        #    form, which arXiv IDs never do, so this is unambiguous.
        try:
            uuid = UUID(paper_ref)
            paper = self.get_by_id(uuid)
            if paper is not None:
                return paper
        except (ValueError, AttributeError):
            pass

        # 2. Fall back to arXiv ID lookup.
        return self.get_by_arxiv_id(paper_ref)

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        stmt = select(Paper).order_by(Paper.published_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def search(
        self,
        filters: PaperSearchFilters,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Paper], int]:
        stmt = select(Paper)

        # ---- Full-text search ----
        if filters.query:
            ts_query = func.plainto_tsquery("english", filters.query)
            rank_expr = func.ts_rank_cd(Paper.search_vector, ts_query)

            stmt = stmt.where(Paper.search_vector.op("@@")(ts_query)).order_by(
                rank_expr.desc(),
                Paper.published_date.desc(),
            )
        else:
            stmt = stmt.order_by(Paper.published_date.desc())

        # ---- Category filter ----
        if filters.categories:
            stmt = stmt.where(or_(*[Paper.categories.contains([cat]) for cat in filters.categories]))

        # ---- PDF processed filter ----
        if filters.pdf_processed is not None:
            stmt = stmt.where(Paper.pdf_processed == filters.pdf_processed)

        # ---- Date range filters ----
        if filters.published_after:
            stmt = stmt.where(Paper.published_date >= filters.published_after)

        if filters.published_before:
            stmt = stmt.where(Paper.published_date <= filters.published_before)

        if filters.source:
            stmt = stmt.where(Paper.source == filters.source)

        # ---- Total count (before pagination) ----
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        # ---- Pagination ----
        stmt = stmt.limit(limit).offset(offset)

        return list(self.session.scalars(stmt)), total

    def get_count(self) -> int:
        stmt = select(func.count(Paper.id))
        return self.session.scalar(stmt) or 0

    def get_processed_papers(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        """Get papers that have been successfully processed with PDF content."""
        stmt = (
            select(Paper)
            .where(Paper.pdf_processed == True)
            .order_by(Paper.pdf_processing_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt))

    def get_unprocessed_papers(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        """Get papers that haven't been processed for PDF content yet."""
        stmt = select(Paper).where(Paper.pdf_processed == False).order_by(Paper.published_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_papers_with_raw_text(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        """Get papers that have raw text content stored."""
        stmt = select(Paper).where(Paper.raw_text != None).order_by(Paper.pdf_processing_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_processing_stats(self) -> dict:
        """Get statistics about PDF processing status."""
        total_papers = self.get_count()

        processed_stmt = select(func.count(Paper.id)).where(Paper.pdf_processed == True)
        processed_papers = self.session.scalar(processed_stmt) or 0

        text_stmt = select(func.count(Paper.id)).where(Paper.raw_text != None)
        papers_with_text = self.session.scalar(text_stmt) or 0

        return {
            "total_papers": total_papers,
            "processed_papers": processed_papers,
            "papers_with_text": papers_with_text,
            "processing_rate": (processed_papers / total_papers * 100) if total_papers > 0 else 0,
            "text_extraction_rate": (papers_with_text / processed_papers * 100) if processed_papers > 0 else 0,
        }

    def update(self, paper: Paper) -> Paper:
        self.session.add(paper)
        self.session.commit()
        self.session.refresh(paper)
        return paper

    def upsert(self, paper_create: PaperCreate) -> Paper:
        existing_paper = self.get_by_arxiv_id(paper_create.arxiv_id)
        if existing_paper:
            for key, value in paper_create.model_dump(exclude_unset=True).items():
                setattr(existing_paper, key, value)
            return self.update(existing_paper)
        else:
            return self.create(paper_create)

    def delete(self, paper: Paper) -> None:
        """Hard-delete a paper record from Postgres.

        Caller is responsible for cleaning up OpenSearch chunks and
        any files on disk before calling this.

        :param paper: Paper ORM instance to delete
        """
        self.session.delete(paper)
        self.session.commit()
