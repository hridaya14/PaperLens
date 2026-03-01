from redis.asyncio import Redis, ConnectionPool
from src.config import get_settings

settings = get_settings()
_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
            max_connections=10,
        )
    return _pool


def get_redis_client() -> Redis:
    return Redis(connection_pool=get_redis_pool())
