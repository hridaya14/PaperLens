"""
Redis cache for flashcard sets.

Follows the same pattern as MindMapCache.
Stores complete FlashcardSet objects with TTL and hit tracking.

Location: src/services/visualization/flashcards/cache.py
"""

import json
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis
from src.config import get_settings
from src.schemas.visualization.flashcards import (
    FlashcardCacheStatus,
    FlashcardSet,
    FlashcardSetCacheEntry,
)

settings = get_settings()

CACHE_KEY_PREFIX = "flashcard_set"


def _cache_key(paper_id: str) -> str:
    """
    Generate Redis key for flashcard set.

    Format: flashcard_set:v{version}:{paper_id}
    """
    version = getattr(settings, "redis_flashcard_cache_version", 1)
    return f"{CACHE_KEY_PREFIX}:v{version}:{paper_id}"


class FlashcardCache:
    """Redis cache for flashcard sets."""

    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    async def get(self, paper_id: str) -> FlashcardSet | None:
        """
        Get flashcard set from cache.

        Increments hit count without resetting TTL.

        Args:
            paper_id: UUID of the paper

        Returns:
            FlashcardSet if cached and not expired, None otherwise
        """
        key = _cache_key(paper_id)
        raw = await self._redis.get(key)

        if raw is None:
            return None

        # Parse cache entry
        entry = FlashcardSetCacheEntry.model_validate_json(raw)

        # Increment hit count without resetting TTL
        entry.hit_count += 1
        ttl = await self._redis.ttl(key)

        # Default TTL from settings
        default_ttl = getattr(settings, "redis_flashcard_ttl_seconds", 86400)  # 24h default

        await self._redis.set(key, entry.model_dump_json(), ex=ttl if ttl > 0 else default_ttl)

        return entry.flashcard_set

    async def set(self, flashcard_set: FlashcardSet) -> None:
        """
        Store flashcard set in cache with TTL.

        Args:
            flashcard_set: Complete flashcard set to cache
        """
        key = _cache_key(flashcard_set.paper_id)
        now = datetime.now(timezone.utc)

        # Default TTL from settings
        default_ttl = getattr(settings, "redis_flashcard_ttl_seconds", 86400)  # 24h
        version = getattr(settings, "redis_flashcard_cache_version", 1)

        # Create cache entry
        entry = FlashcardSetCacheEntry(
            flashcard_set=flashcard_set,
            cache_version=version,
            hit_count=0,
            cached_at=now,
            expires_at=now + timedelta(seconds=default_ttl),
        )

        # Store in Redis
        await self._redis.set(
            key,
            entry.model_dump_json(),
            ex=default_ttl,
        )

    async def invalidate(self, paper_id: str) -> None:
        """
        Remove flashcard set from cache.

        Args:
            paper_id: UUID of the paper
        """
        key = _cache_key(paper_id)
        await self._redis.delete(key)

    async def status(self, paper_id: str) -> FlashcardCacheStatus:
        """
        Get cache status for a flashcard set.

        Args:
            paper_id: UUID of the paper

        Returns:
            FlashcardCacheStatus with cache metadata
        """
        key = _cache_key(paper_id)
        raw = await self._redis.get(key)

        if raw is None:
            return FlashcardCacheStatus(paper_id=paper_id, is_cached=False)

        entry = FlashcardSetCacheEntry.model_validate_json(raw)
        ttl = await self._redis.ttl(key)

        return FlashcardCacheStatus(
            paper_id=paper_id,
            is_cached=True,
            num_cards=entry.flashcard_set.total_cards,
            cached_at=entry.cached_at,
            expires_at=entry.expires_at,
            ttl_seconds=ttl if ttl > 0 else None,
        )
