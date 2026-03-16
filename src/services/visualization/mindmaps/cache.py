import json
from datetime import datetime, timedelta, timezone
from redis.asyncio import Redis
from src.schemas.visualization.mindmaps import MindMap, MindMapCacheEntry, MindMapCacheStatus
from src.config import get_settings

settings = get_settings()

CACHE_KEY_PREFIX = "mindmap"


def _cache_key(paper_id: str) -> str:
    return f"{CACHE_KEY_PREFIX}:v{settings.redis_mindmap_cache_version}:{paper_id}"


class MindMapCache:
    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    async def get(self, paper_id: str) -> MindMap | None:
        key = _cache_key(paper_id)
        raw = await self._redis.get(key)

        if raw is None:
            return None

        entry = MindMapCacheEntry.model_validate_json(raw)

        # increment hit count without resetting TTL
        entry.hit_count += 1
        ttl = await self._redis.ttl(key)
        await self._redis.set(key, entry.model_dump_json(), ex=ttl if ttl > 0 else settings.redis_mindmap_ttl_seconds)

        return entry.mindmap

    async def set(self, mindmap: MindMap) -> None:
        key = _cache_key(mindmap.paper_id)
        now = datetime.now(timezone.utc)

        entry = MindMapCacheEntry(
            mindmap=mindmap,
            cache_version=settings.redis_mindmap_cache_version,
            hit_count=0,
            cached_at=now,
            expires_at=now + timedelta(seconds=settings.redis_mindmap_ttl_seconds),
        )

        await self._redis.set(
            key,
            entry.model_dump_json(),
            ex=settings.redis_mindmap_ttl_seconds,
        )

    async def invalidate(self, paper_id: str) -> None:
        await self._redis.delete(_cache_key(paper_id))

    async def status(self, paper_id: str) -> MindMapCacheStatus:
        key = _cache_key(paper_id)
        raw = await self._redis.get(key)

        if raw is None:
            return MindMapCacheStatus(paper_id=paper_id, is_cached=False)

        entry = MindMapCacheEntry.model_validate_json(raw)
        ttl = await self._redis.ttl(key)

        return MindMapCacheStatus(
            paper_id=paper_id,
            is_cached=True,
            hit_count=entry.hit_count,
            cached_at=entry.cached_at,
            expires_at=entry.expires_at,
            ttl_seconds=ttl if ttl > 0 else None,
        )
