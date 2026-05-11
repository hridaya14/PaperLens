import logging
import sys
from functools import lru_cache
from typing import Any, Tuple

sys.path.insert(0, "/opt/airflow")

from src.db.factory import make_database
from src.services.arxiv.factory import make_arxiv_client
from src.services.embeddings.factory import make_embeddings_client
from src.services.metadata_fetcher import make_metadata_fetcher
from src.services.nvidia.factory import make_nvidia_client
from src.services.opensearch.factory import make_opensearch_client
from src.services.pdf_parser.factory import make_pdf_parser_service

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_cached_services() -> Tuple[Any, Any, Any, Any, Any]:
    """Get cached service instances using lru_cache for automatic memoization.

    Unchanged from original — tuple position contract preserved so all
    existing callers continue to work without modification.

    :returns: Tuple of (arxiv_client, pdf_parser, database, metadata_fetcher, opensearch_client)
    """
    logger.info("Initializing services (cached with lru_cache)")

    arxiv_client = make_arxiv_client()
    pdf_parser = make_pdf_parser_service()
    database = make_database()
    opensearch_client = make_opensearch_client()
    metadata_fetcher = make_metadata_fetcher(arxiv_client, pdf_parser)

    logger.info("All services initialized and cached with lru_cache")
    return arxiv_client, pdf_parser, database, metadata_fetcher, opensearch_client


@lru_cache(maxsize=1)
def get_filtering_services() -> Tuple[Any, Any]:
    """Get cached filtering service instances.

    Kept separate from get_cached_services() so:
    - Existing callers are unaffected
    - Filtering services are only initialised when the filter task runs
    - lru_cache keeps client objects alive for the worker process lifetime

    :returns: Tuple of (embeddings_client, llm_client)
    """
    logger.info("Initializing filtering services (cached with lru_cache)")

    embeddings_client = make_embeddings_client()
    llm_client = make_nvidia_client()

    logger.info("Filtering services initialized and cached")
    return embeddings_client, llm_client
