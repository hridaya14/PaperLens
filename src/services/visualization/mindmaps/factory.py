from src.services.visualization.mindmaps.generator import MindMapGenerator
from src.services.visualization.mindmaps.cache import MindMapCache
from src.services.visualization.mindmaps.client import MindMapService
from src.services.nvidia.factory import make_nvidia_client
from src.db.redis.redis import get_redis_client


def get_mindmap_service() -> MindMapService:
    generator = MindMapGenerator(nvidia_client=make_nvidia_client())
    cache = MindMapCache(redis_client=get_redis_client())
    return MindMapService(generator=generator, cache=cache)
