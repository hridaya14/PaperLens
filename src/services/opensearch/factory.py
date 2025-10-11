from functools import lru_cache

from src.config import get_settings

from .client import OpenSearchClient


@lru_cache(maxsize=1)
def make_opensearch_client() -> OpenSearchClient:
    """
    Uses lru_cache to maintain a singleton instance, consistent with
    other service factories in the codebase.
    """
    settings = get_settings()
    return OpenSearchClient(host=settings.opensearch.host, settings=settings)