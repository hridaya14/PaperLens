from functools import lru_cache
from typing import Annotated, Generator

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.orm import Session
from src.config import Settings
from src.db.interfaces.base import BaseDatabase
from src.repositories.flashcards import FlashcardRepository
from src.services.arxiv.client import ArxivClient
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.nvidia.client import NvidiaClient
from src.services.opensearch.client import OpenSearchClient
from src.services.pdf_parser.parser import PDFParserService
from src.services.visualization.flashcards import FlashcardCache, FlashcardGenerator, FlashcardService
from src.services.visualization.mindmaps.client import MindMapService


@lru_cache
def get_settings() -> Settings:
    """Get application settings."""
    return Settings()


def get_request_settings(request: Request) -> Settings:
    """Get settings from the request state."""
    return request.app.state.settings


def get_database(request: Request) -> BaseDatabase:
    """Get database from the request state."""
    return request.app.state.database


def get_db_session(database: Annotated[BaseDatabase, Depends(get_database)]) -> Generator[Session, None, None]:
    """Get database session dependency."""
    with database.get_session() as session:
        yield session


def get_opensearch_client(request: Request) -> OpenSearchClient:
    """Get OpenSearch client from the request state."""
    return request.app.state.opensearch_client


def get_arxiv_client(request: Request) -> ArxivClient:
    """Get arXiv client from the request state."""
    return request.app.state.arxiv_client


def get_pdf_parser(request: Request) -> PDFParserService:
    """Get PDF parser service from the request state."""
    return request.app.state.pdf_parser


def get_embeddings_service(request: Request) -> JinaEmbeddingsClient:
    """Get embeddings service from the request state."""
    return request.app.state.embeddings_service


def get_nvidia_client(request: Request) -> NvidiaClient:
    """Get nvidia client from the request state."""
    return request.app.state.nvidia_client


def get_redis_client(request: Request) -> Redis:
    """Get redis client from the request state"""
    return request.app.state.redis_client


def get_mindmap_client(request: Request) -> MindMapService:
    """Get Mindmap client from the request state"""
    return request.app.state.mindmap_client


def get_flashcard_service(
    db=Depends(get_db_session),
    redis=Depends(get_redis_client),
    nvidia=Depends(get_nvidia_client),
) -> FlashcardService:

    generator = FlashcardGenerator(nvidia_client=nvidia)

    cache = FlashcardCache(redis_client=redis)

    repository = FlashcardRepository(session=db)

    return FlashcardService(
        generator=generator,
        cache=cache,
        repository=repository,
    )


# Dependency annotations
SettingsDep = Annotated[Settings, Depends(get_settings)]
DatabaseDep = Annotated[BaseDatabase, Depends(get_database)]
SessionDep = Annotated[Session, Depends(get_db_session)]
OpenSearchDep = Annotated[OpenSearchClient, Depends(get_opensearch_client)]
MindMapDep = Annotated[MindMapService, Depends(get_mindmap_client)]
ArxivDep = Annotated[ArxivClient, Depends(get_arxiv_client)]
PDFParserDep = Annotated[PDFParserService, Depends(get_pdf_parser)]
EmbeddingsDep = Annotated[JinaEmbeddingsClient, Depends(get_embeddings_service)]
NvidiaDep = Annotated[NvidiaClient, Depends(get_nvidia_client)]
RedisDep = Annotated[Redis, Depends(get_redis_client)]
FlashCardDep = Annotated[FlashcardService, Depends(get_flashcard_service)]
