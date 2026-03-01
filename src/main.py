import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from src.config import get_settings
from src.db.factory import make_database
from src.routers import hybrid_search, ping, papers, visualization
from src.routers.ask import ask_router, stream_router
from src.services.arxiv.factory import make_arxiv_client
from src.services.opensearch.factory import make_opensearch_client
from src.services.embeddings.factory import make_embeddings_service
from src.services.nvidia.factory import make_nvidia_client
from src.services.pdf_parser.factory import make_pdf_parser_service
from src.db.redis.redis import get_redis_client
from src.services.visualization.mindmaps.factory import get_mindmap_service

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan for the API.
    """
    logger.info("Starting RAG API...")

    settings = get_settings()
    app.state.settings = settings

    # Initialize DB
    database = make_database()
    app.state.database = database
    logger.info("Database connected")

    # Initialize Redis Cache Client
    redis_client = get_redis_client()
    app.state.redis_client = redis_client
    logger.info("Redis client connected")

    # Initialize search service
    opensearch_client = make_opensearch_client()
    app.state.opensearch_client = opensearch_client

    # Verify OpenSearch connectivity and create index if needed
    if opensearch_client.health_check():
        logger.info("OpenSearch connected successfully")

        # Setup hybrid index (supports all search types)
        setup_results = opensearch_client.setup_indices(force=False)
        if setup_results.get("hybrid_index"):
            logger.info("Hybrid index created")
        else:
            logger.info("Hybrid index already exists")

        # Get simple statistics
        try:
            stats = opensearch_client.client.count(
                index=opensearch_client.index_name)
            logger.info(f"OpenSearch ready: {
                        stats['count']} documents indexed")
        except Exception:
            logger.info("OpenSearch index ready (stats unavailable)")
    else:
        logger.warning(
            "OpenSearch connection failed - search features will be limited")

    # Initialize other services (kept for future endpoints and notebook demos)
    app.state.arxiv_client = make_arxiv_client()
    app.state.pdf_parser = make_pdf_parser_service()
    app.state.embeddings_service = make_embeddings_service()
    app.state.nvidia_client = make_nvidia_client()
    app.state.mindmap_client = get_mindmap_service()
    logger.info(
        "Services initialized: arXiv API client, PDF parser, OpenSearch, Embeddings, Nvidia")
    logger.info("API ready")
    yield

    # Cleanup
    database.teardown()
    logger.info("API shutdown complete")


app = FastAPI(
    title="arXiv Paper Curator API",
    description="Personal arXiv paper curator with Visualization, Detailed Analysis and RAG Features",
    version=os.getenv("APP_VERSION", "0.1.0"),
    lifespan=lifespan,
)

# Routers
app.include_router(ping.router, prefix="/api/v1")  # Health check endpoint
app.include_router(papers.router, prefix="/api/v1")
# Search chunks with BM25/hybrid
app.include_router(hybrid_search.router, prefix="/api/v1")

# Visualization Routers
app.include_router(visualization.router, prefix="/api/v1")

# RAG question answering with LLM
app.include_router(ask_router, prefix="/api/v1")
app.include_router(stream_router, prefix="/api/v1")  # Streaming RAG responses


if __name__ == "__main__":
    uvicorn.run(app, port=8000, host="0.0.0.0")
