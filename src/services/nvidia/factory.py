from functools import lru_cache

from src.config import get_settings
from src.services.nvidia.client import NvidiaClient


@lru_cache(maxsize=1)
def make_nvidia_client() -> NvidiaClient:
    """
    Create and return a singleton Ollama client instance.

    Returns:
        OllamaClient: Configured Ollama client
    """
    return NvidiaClient()
