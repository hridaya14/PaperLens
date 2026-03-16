"""
Flashcard service - main orchestration layer.

Coordinates cache, database, and generation for flashcard sets.
Follows the same pattern as MindMapService.

Location: src/services/visualization/flashcards/client.py
"""

import logging
from typing import List, Optional

from src.repositories.flashcards import FlashcardRepository
from src.schemas.visualization.flashcards import FlashcardCacheStatus, FlashcardSet
from src.services.visualization.flashcards.cache import FlashcardCache
from src.services.visualization.flashcards.generator import (
    FlashcardGenerationError,
    FlashcardGenerator,
)

logger = logging.getLogger(__name__)


class FlashcardService:
    """
    Main service for flashcard generation and retrieval.

    Orchestrates:
    1. Redis cache (hot layer)
    2. Database (persistent layer)
    3. LLM generation (on-demand)
    """

    def __init__(
        self,
        generator: FlashcardGenerator,
        cache: FlashcardCache,
        repository: FlashcardRepository,
    ):
        self._generator = generator
        self._cache = cache
        self._repo = repository

    async def get_or_generate(
        self,
        paper_id: str,
        arxiv_id: Optional[str],
        paper_title: str,
        paper_abstract: str,
        chunks: list,
        num_cards: int = 15,
        topics: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> FlashcardSet:
        """
        Get flashcard set from cache/DB or generate new one.

        Flow:
        1. Check Redis cache (if not force_refresh)
        2. Check DB freshness
        3. Generate if needed
        4. Store in DB + cache

        Args:
            paper_id: UUID of the paper
            arxiv_id: ArXiv ID (optional)
            paper_title: Paper title
            paper_abstract: Paper abstract
            chunks: Text chunks from paper
            num_cards: Number of flashcards to generate
            topics: Optional topics to focus on
            force_refresh: Skip cache and regenerate

        Returns:
            FlashcardSet with all flashcards

        Raises:
            FlashcardGenerationError: If generation fails
        """

        # =====================================================================
        # Step 1: Check Redis cache (hot layer)
        # =====================================================================

        if not force_refresh:
            cached = await self._cache.get(paper_id)
            if cached:
                logger.info("Flashcard set cache hit (Redis)", extra={"paper_id": paper_id})
                return cached

        logger.info("Flashcard set cache miss — checking database", extra={"paper_id": paper_id})

        # =====================================================================
        # Step 2: Check DB freshness
        # =====================================================================

        freshness = self._repo.check_set_freshness(paper_id)

        if freshness["exists"] and freshness["is_fresh"] and not force_refresh:
            # Flashcard set exists in DB and is fresh
            logger.info(
                "Flashcard set found in DB (fresh)",
                extra={
                    "paper_id": paper_id,
                    "total_cards": freshness["total_cards"],
                    "expires_at": freshness["expires_at"],
                },
            )

            # Load from DB
            flashcard_set = self._load_from_db(paper_id)

            # Cache in Redis for future requests
            await self._cache.set(flashcard_set)

            return flashcard_set

        # =====================================================================
        # Step 3: Generate new flashcards
        # =====================================================================

        if freshness["exists"]:
            logger.info("Flashcard set in DB is stale — regenerating", extra={"paper_id": paper_id})
        else:
            logger.info("Flashcard set not found — generating", extra={"paper_id": paper_id})

        # Generate flashcard set via LLM
        flashcard_set = await self._generator.generate(
            paper_id=paper_id,
            arxiv_id=arxiv_id,
            paper_title=paper_title,
            paper_abstract=paper_abstract,
            chunks=chunks,
            num_cards=num_cards,
            topics=topics,
        )

        # =====================================================================
        # Step 4: Store in DB (persistent layer)
        # =====================================================================

        # ✅ FIX: Capture the returned FlashcardSet with database IDs
        flashcard_set = self._store_in_db(flashcard_set)

        logger.info("Flashcard set stored in database", extra={"paper_id": paper_id, "total_cards": flashcard_set.total_cards})

        # =====================================================================
        # Step 5: Cache in Redis (hot layer)
        # =====================================================================

        await self._cache.set(flashcard_set)

        logger.info("Flashcard set cached in Redis", extra={"paper_id": paper_id})

        return flashcard_set

    async def invalidate(self, paper_id: str) -> None:
        """
        Invalidate flashcard set from cache and optionally DB.

        Args:
            paper_id: UUID of the paper
        """
        # Remove from Redis cache
        await self._cache.invalidate(paper_id)

        # Remove from database
        self._repo.delete_by_paper_id(paper_id)

        logger.info("Flashcard set invalidated", extra={"paper_id": paper_id})

    async def get_cache_status(self, paper_id: str) -> FlashcardCacheStatus:
        """
        Get cache status for a flashcard set.

        Args:
            paper_id: UUID of the paper

        Returns:
            FlashcardCacheStatus
        """
        return await self._cache.status(paper_id)

    def get_db_status(self, paper_id: str) -> dict:
        """
        Get database status for a flashcard set.

        Args:
            paper_id: UUID of the paper

        Returns:
            Dict with freshness info
        """
        return self._repo.check_set_freshness(paper_id)

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _load_from_db(self, paper_id: str) -> FlashcardSet:
        """
        Load flashcard set from database.

        Args:
            paper_id: UUID of the paper

        Returns:
            FlashcardSet reconstructed from DB records
        """
        # Get metadata
        metadata = self._repo.get_set_metadata(paper_id)
        if not metadata:
            raise FlashcardGenerationError(f"Flashcard metadata not found for paper_id={paper_id}")

        # Get all flashcards
        flashcard_models = self._repo.get_by_paper_id(paper_id)

        # Convert DB models to Pydantic schema
        from src.schemas.visualization.flashcards import Flashcard

        flashcards = [
            Flashcard(
                id=fc.id,
                paper_id=str(fc.paper_id),
                front=fc.front,
                back=fc.back,
                topic=fc.topic,
                difficulty=fc.difficulty,
                card_index=fc.card_index,
                generated_at=fc.generated_at,
            )
            for fc in flashcard_models
        ]

        # Build FlashcardSet
        flashcard_set = FlashcardSet(
            paper_id=str(metadata.paper_id),
            arxiv_id=metadata.arxiv_id,
            paper_title=metadata.paper_title,
            flashcards=flashcards,
            total_cards=metadata.total_cards,
            generated_at=metadata.generated_at,
            expires_at=metadata.expires_at,
            model_used=metadata.model_used,
        )

        return flashcard_set

    def _store_in_db(self, flashcard_set: FlashcardSet) -> FlashcardSet:
        """
        Store flashcard set in database and return with populated IDs.

        Args:
            flashcard_set: Complete flashcard set to store (flashcards have id=None)

        Returns:
            FlashcardSet with flashcards containing database-generated IDs
        """
        # Convert FlashcardSet to DB-friendly format
        flashcard_dicts = [
            {
                "front": fc.front,
                "back": fc.back,
                "topic": fc.topic,
                "difficulty": fc.difficulty,
                "card_index": fc.card_index,
            }
            for fc in flashcard_set.flashcards
        ]

        # Calculate TTL (expires_at - generated_at)
        ttl_delta = flashcard_set.expires_at - flashcard_set.generated_at
        ttl_days = int(ttl_delta.total_seconds() / 86400)

        # Upsert flashcard set (replaces old if exists)
        # Repository already calls session.refresh(), so models have database IDs
        flashcard_models, metadata_model = self._repo.upsert_flashcard_set(
            paper_id=flashcard_set.paper_id,
            arxiv_id=flashcard_set.arxiv_id,
            paper_title=flashcard_set.paper_title,
            flashcards=flashcard_dicts,
            model_used=flashcard_set.model_used,
            ttl_days=ttl_days,
        )

        from src.schemas.visualization.flashcards import Flashcard

        flashcards_with_ids = [
            Flashcard(
                id=fc.id,
                paper_id=str(fc.paper_id),
                front=fc.front,
                back=fc.back,
                topic=fc.topic,
                difficulty=fc.difficulty,
                card_index=fc.card_index,
                generated_at=fc.generated_at,
            )
            for fc in flashcard_models
        ]

        return FlashcardSet(
            paper_id=flashcard_set.paper_id,
            arxiv_id=flashcard_set.arxiv_id,
            paper_title=flashcard_set.paper_title,
            flashcards=flashcards_with_ids,
            total_cards=len(flashcards_with_ids),
            generated_at=flashcard_set.generated_at,
            expires_at=flashcard_set.expires_at,
            model_used=flashcard_set.model_used,
        )
