"""
Flashcard repository for NotebookLM-style flashcards.

Multiple flashcards per paper, each covering a specific concept/topic.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from src.models.flashcards import Flashcard as FlashcardModel
from src.models.flashcards import FlashcardSetMetadata as FlashcardSetMetadataModel

logger = logging.getLogger(__name__)


class FlashcardRepository:
    """Repository for flashcard database operations."""

    def __init__(self, session: Session):
        self.session = session

    # =========================================================================
    # Read Operations - Individual Flashcards
    # =========================================================================

    def get_by_id(self, flashcard_id: int) -> Optional[FlashcardModel]:
        """Get single flashcard by ID."""
        stmt = select(FlashcardModel).where(FlashcardModel.id == flashcard_id)
        return self.session.scalar(stmt)

    def get_by_paper_id(self, paper_id: str, limit: Optional[int] = None) -> List[FlashcardModel]:
        """
        Get all flashcards for a specific paper.

        Returns cards in order (by card_index).
        """
        stmt = select(FlashcardModel).where(FlashcardModel.paper_id == paper_id).order_by(FlashcardModel.card_index.asc())

        if limit:
            stmt = stmt.limit(limit)

        return list(self.session.scalars(stmt))

    def get_by_paper_id_and_topic(self, paper_id: str, topic: str) -> List[FlashcardModel]:
        """Get flashcards for a paper filtered by topic."""
        stmt = (
            select(FlashcardModel)
            .where(FlashcardModel.paper_id == paper_id, FlashcardModel.topic == topic)
            .order_by(FlashcardModel.card_index.asc())
        )

        return list(self.session.scalars(stmt))

    def get_by_difficulty(self, paper_id: str, difficulty: str) -> List[FlashcardModel]:
        """Get flashcards for a paper filtered by difficulty."""
        stmt = (
            select(FlashcardModel)
            .where(FlashcardModel.paper_id == paper_id, FlashcardModel.difficulty == difficulty)
            .order_by(FlashcardModel.card_index.asc())
        )

        return list(self.session.scalars(stmt))

    # =========================================================================
    # Read Operations - Set Metadata
    # =========================================================================

    def get_set_metadata(self, paper_id: str) -> Optional[FlashcardSetMetadataModel]:
        """Get metadata for a paper's flashcard set."""
        stmt = select(FlashcardSetMetadataModel).where(FlashcardSetMetadataModel.paper_id == paper_id)
        return self.session.scalar(stmt)

    def check_set_freshness(self, paper_id: str) -> dict:
        """
        Check if flashcard set exists and is fresh.

        Returns:
            {
                "exists": bool,
                "is_fresh": bool,
                "total_cards": int or None,
                "generated_at": datetime or None,
                "expires_at": datetime or None
            }
        """
        metadata = self.get_set_metadata(paper_id)

        if metadata is None:
            return {
                "exists": False,
                "is_fresh": False,
                "total_cards": None,
                "generated_at": None,
                "expires_at": None,
            }

        now = datetime.now(timezone.utc)
        is_fresh = metadata.expires_at > now

        return {
            "exists": True,
            "is_fresh": is_fresh,
            "total_cards": metadata.total_cards,
            "generated_at": metadata.generated_at,
            "expires_at": metadata.expires_at,
        }

    def list_all_metadata(self, only_fresh: bool = True, limit: int = 100, offset: int = 0) -> List[FlashcardSetMetadataModel]:
        """List all flashcard set metadata (for admin/stats)."""
        stmt = select(FlashcardSetMetadataModel)

        if only_fresh:
            stmt = stmt.where(FlashcardSetMetadataModel.expires_at > datetime.now(timezone.utc))

        stmt = stmt.order_by(FlashcardSetMetadataModel.generated_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        return list(self.session.scalars(stmt))

    # =========================================================================
    # Write Operations - Create Flashcard Set
    # =========================================================================

    def create_flashcard_set(
        self,
        paper_id: str,
        arxiv_id: Optional[str],
        paper_title: str,
        flashcards: List[dict],  # List of {front, back, topic, difficulty, card_index}
        model_used: str,
        ttl_days: int = 7,
    ) -> tuple[List[FlashcardModel], FlashcardSetMetadataModel]:
        """
        Create a complete flashcard set for a paper.

        This is the main method for flashcard generation.
        Creates both individual flashcards and set metadata.

        Args:
            paper_id: UUID of paper
            arxiv_id: ArXiv ID (optional)
            paper_title: Title of paper
            flashcards: List of flashcard dicts
            model_used: LLM model name
            ttl_days: Days until flashcards expire

        Returns:
            (flashcard_models, metadata_model)
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=ttl_days)

        # 1. Create flashcard records
        flashcard_models = []
        for card_data in flashcards:
            flashcard = FlashcardModel(
                paper_id=paper_id,
                front=card_data["front"],
                back=card_data["back"],
                topic=card_data.get("topic"),
                difficulty=card_data.get("difficulty"),
                card_index=card_data["card_index"],
                generated_at=now,
            )
            self.session.add(flashcard)
            flashcard_models.append(flashcard)

        # 2. Create set metadata
        metadata = FlashcardSetMetadataModel(
            paper_id=paper_id,
            arxiv_id=arxiv_id,
            paper_title=paper_title,
            total_cards=len(flashcards),
            model_used=model_used,
            generated_at=now,
            expires_at=expires_at,
        )
        self.session.add(metadata)

        # 3. Commit everything
        self.session.commit()

        # 4. Refresh to get IDs
        for flashcard in flashcard_models:
            self.session.refresh(flashcard)
        self.session.refresh(metadata)

        logger.info(
            "Flashcard set created", extra={"paper_id": paper_id, "total_cards": len(flashcards), "model_used": model_used}
        )

        return flashcard_models, metadata

    def upsert_flashcard_set(
        self, paper_id: str, arxiv_id: Optional[str], paper_title: str, flashcards: List[dict], model_used: str, ttl_days: int = 7
    ) -> tuple[List[FlashcardModel], FlashcardSetMetadataModel]:
        """
        Upsert a flashcard set (delete old, create new).

        This replaces any existing flashcard set for the paper.
        """
        # Delete existing flashcards and metadata
        self.delete_by_paper_id(paper_id)

        # Create new set
        return self.create_flashcard_set(
            paper_id=paper_id,
            arxiv_id=arxiv_id,
            paper_title=paper_title,
            flashcards=flashcards,
            model_used=model_used,
            ttl_days=ttl_days,
        )

    # =========================================================================
    # Write Operations - Individual Cards
    # =========================================================================

    def create_flashcard(
        self, paper_id: str, front: str, back: str, card_index: int, topic: Optional[str] = None, difficulty: Optional[str] = None
    ) -> FlashcardModel:
        """Create a single flashcard."""
        flashcard = FlashcardModel(
            paper_id=paper_id,
            front=front,
            back=back,
            topic=topic,
            difficulty=difficulty,
            card_index=card_index,
            generated_at=datetime.now(timezone.utc),
        )

        self.session.add(flashcard)
        self.session.commit()
        self.session.refresh(flashcard)

        return flashcard

    def update_flashcard(
        self,
        flashcard_id: int,
        front: Optional[str] = None,
        back: Optional[str] = None,
        topic: Optional[str] = None,
        difficulty: Optional[str] = None,
    ) -> Optional[FlashcardModel]:
        """Update an existing flashcard."""
        flashcard = self.get_by_id(flashcard_id)

        if flashcard is None:
            return None

        if front is not None:
            flashcard.front = front
        if back is not None:
            flashcard.back = back
        if topic is not None:
            flashcard.topic = topic
        if difficulty is not None:
            flashcard.difficulty = difficulty

        self.session.commit()
        self.session.refresh(flashcard)

        return flashcard

    # =========================================================================
    # Delete Operations
    # =========================================================================

    def delete_by_paper_id(self, paper_id: str) -> dict:
        """
        Delete all flashcards and metadata for a paper.

        Returns:
            {"cards_deleted": int, "metadata_deleted": bool}
        """
        # Delete flashcards
        cards_stmt = delete(FlashcardModel).where(FlashcardModel.paper_id == paper_id)
        cards_result = self.session.execute(cards_stmt)
        cards_deleted = cards_result.rowcount

        # Delete metadata
        metadata_stmt = delete(FlashcardSetMetadataModel).where(FlashcardSetMetadataModel.paper_id == paper_id)
        metadata_result = self.session.execute(metadata_stmt)
        metadata_deleted = metadata_result.rowcount > 0

        self.session.commit()

        if cards_deleted > 0 or metadata_deleted:
            logger.info("Flashcard set deleted", extra={"paper_id": paper_id, "cards_deleted": cards_deleted})

        return {"cards_deleted": cards_deleted, "metadata_deleted": metadata_deleted}

    def delete_flashcard(self, flashcard_id: int) -> bool:
        """Delete a single flashcard by ID."""
        stmt = delete(FlashcardModel).where(FlashcardModel.id == flashcard_id)
        result = self.session.execute(stmt)
        self.session.commit()

        return result.rowcount > 0

    def delete_expired_sets(self, older_than_days: int = 30) -> int:
        """
        Delete flashcard sets that expired more than N days ago.

        Returns number of sets deleted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        # Get paper_ids of expired sets
        stmt = select(FlashcardSetMetadataModel.paper_id).where(FlashcardSetMetadataModel.expires_at < cutoff)
        expired_paper_ids = list(self.session.scalars(stmt))

        if not expired_paper_ids:
            return 0

        # Delete flashcards for these papers
        cards_stmt = delete(FlashcardModel).where(FlashcardModel.paper_id.in_(expired_paper_ids))
        self.session.execute(cards_stmt)

        # Delete metadata
        metadata_stmt = delete(FlashcardSetMetadataModel).where(FlashcardSetMetadataModel.paper_id.in_(expired_paper_ids))
        self.session.execute(metadata_stmt)

        self.session.commit()

        deleted_count = len(expired_paper_ids)

        if deleted_count > 0:
            logger.info("Expired flashcard sets deleted", extra={"count": deleted_count, "cutoff": cutoff})

        return deleted_count

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_stats(self) -> dict:
        """Get global flashcard statistics."""
        # Total flashcards
        total_cards = self.session.scalar(select(func.count(FlashcardModel.id))) or 0

        # Total sets
        total_sets = self.session.scalar(select(func.count(FlashcardSetMetadataModel.paper_id))) or 0

        # Fresh sets
        fresh_sets = (
            self.session.scalar(
                select(func.count(FlashcardSetMetadataModel.paper_id)).where(
                    FlashcardSetMetadataModel.expires_at > datetime.now(timezone.utc)
                )
            )
            or 0
        )

        # Average cards per set
        avg_cards = self.session.scalar(select(func.avg(FlashcardSetMetadataModel.total_cards))) or 0

        # Cards by topic (top 10)
        topic_counts = dict(
            self.session.execute(
                select(FlashcardModel.topic, func.count(FlashcardModel.id))
                .where(FlashcardModel.topic.isnot(None))
                .group_by(FlashcardModel.topic)
                .order_by(func.count(FlashcardModel.id).desc())
                .limit(10)
            ).all()
        )

        return {
            "total_flashcards": total_cards,
            "total_sets": total_sets,
            "fresh_sets": fresh_sets,
            "stale_sets": total_sets - fresh_sets,
            "avg_cards_per_set": round(float(avg_cards), 1),
            "top_topics": topic_counts,
        }

    def get_paper_stats(self, paper_id: str) -> dict:
        """Get statistics for a specific paper's flashcard set."""
        metadata = self.get_set_metadata(paper_id)

        if metadata is None:
            return {"exists": False}

        # Count by topic
        topic_counts = dict(
            self.session.execute(
                select(FlashcardModel.topic, func.count(FlashcardModel.id))
                .where(FlashcardModel.paper_id == paper_id)
                .group_by(FlashcardModel.topic)
            ).all()
        )

        # Count by difficulty
        difficulty_counts = dict(
            self.session.execute(
                select(FlashcardModel.difficulty, func.count(FlashcardModel.id))
                .where(FlashcardModel.paper_id == paper_id)
                .group_by(FlashcardModel.difficulty)
            ).all()
        )

        return {
            "exists": True,
            "total_cards": metadata.total_cards,
            "is_fresh": metadata.expires_at > datetime.now(timezone.utc),
            "generated_at": metadata.generated_at,
            "expires_at": metadata.expires_at,
            "model_used": metadata.model_used,
            "by_topic": topic_counts,
            "by_difficulty": difficulty_counts,
        }
