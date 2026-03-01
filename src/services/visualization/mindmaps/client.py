import logging
from src.schemas.visualization.mindmaps import MindMap, MindMapCacheStatus
from src.services.visualization.mindmaps.generator import MindMapGenerator, MindMapGenerationError
from src.services.visualization.mindmaps.cache import MindMapCache

logger = logging.getLogger(__name__)


class MindMapService:
    def __init__(self, generator: MindMapGenerator, cache: MindMapCache):
        self._generator = generator
        self._cache = cache

    async def get_or_generate(
        self,
        paper_id: str,
        arxiv_id: str,
        paper_title: str,
        chunks: list,
    ) -> MindMap:
        # 1. Cache check
        cached = await self._cache.get(paper_id)
        if cached:
            logger.info("Mind map cache hit", extra={"paper_id": paper_id})
            return cached

        logger.info("Mind map cache miss — generating", extra={"paper_id": paper_id})

        # 2. Generate
        mindmap = await self._generator.generate(
            paper_id=paper_id,
            arxiv_id=arxiv_id,
            chunks=chunks,
            paper_title=paper_title
        )

        # Override title from paper record (more reliable than chunk inference)
        mindmap.paper_title = paper_title

        # 3. Cache and return
        await self._cache.set(mindmap)
        logger.info("Mind map generated and cached", extra={"paper_id": paper_id})

        return mindmap

    async def invalidate(self, paper_id: str) -> None:
        await self._cache.invalidate(paper_id)
        logger.info("Mind map cache invalidated", extra={"paper_id": paper_id})

    async def get_cache_status(self, paper_id: str) -> MindMapCacheStatus:
        return await self._cache.status(paper_id)
