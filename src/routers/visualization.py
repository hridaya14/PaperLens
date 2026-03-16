"""
Visualization API router - Mind Maps and Flashcards.

Unified endpoints for paper visualizations and study tools.

Location: src/routers/visualization.py
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session
from src.dependencies import FlashCardDep, MindMapDep, OpenSearchDep, SessionDep
from src.repositories.paper import PaperRepository
from src.schemas.visualization.flashcards import (
    FlashcardCacheStatus,
    FlashcardResponse,
    FlashcardSetResponse,
)
from src.schemas.visualization.mindmaps import MindMap, MindMapCacheStatus
from src.services.opensearch.client import OpenSearchClient
from src.services.visualization.flashcards.generator import FlashcardGenerationError
from src.services.visualization.mindmaps.generator import MindMapGenerationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/visualization", tags=["visualization"])


# =============================================================================
# Mind Map Endpoints
# =============================================================================


@router.get(
    "/{paper_id}/mindmap",
    response_model=MindMap,
    summary="Get or generate a mind map for a paper",
)
async def get_mindmap(
    mindmap_service: MindMapDep,
    opensearch: OpenSearchDep,
    db: SessionDep,
    paper_id: str = Path(
        ..., description="arXiv paper ID (e.g., '2401.00001' or '2401.00001v1')", regex=r"^\d{4}\.\d{4,5}(v\d+)?$"
    ),
):
    """Get or generate mind map for a paper."""
    paper_repo = PaperRepository(db)

    # 1. Verify paper exists and get title
    paper = paper_repo.get_by_arxiv_id(paper_id)
    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper {paper_id} not found",
        )

    # 2. Fetch all chunks for this paper from OpenSearch
    chunks = opensearch.get_chunks_by_paper(paper_id)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No chunks found for paper {paper_id} — paper may not be fully indexed yet",
        )

    # 3. Get or generate mind map
    try:
        mindmap = await mindmap_service.get_or_generate(
            paper_id=paper_id,
            arxiv_id=paper.arxiv_id,
            paper_title=paper.title,
            chunks=chunks,
        )
    except MindMapGenerationError as e:
        logger.error("Mind map generation failed", extra={"paper_id": str(paper_id), "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Mind map generation failed: {e}",
        )

    return mindmap


@router.get(
    "/{paper_id}/mindmap/status",
    response_model=MindMapCacheStatus,
    summary="Check whether a mind map is cached for a paper",
)
async def get_mindmap_cache_status(
    paper_id: str,
    mindmap_service: MindMapDep,
):
    """Check mind map cache status."""
    return await mindmap_service.get_cache_status(paper_id)


@router.delete(
    "/{paper_id}/mindmap",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate cached mind map for a paper",
)
async def invalidate_mindmap(
    paper_id: str,
    mindmap_service: MindMapDep,
):
    """Delete mind map from cache."""
    await mindmap_service.invalidate(str(paper_id))


# =============================================================================
# Flashcard Endpoints
# =============================================================================


@router.get(
    "/{paper_id}/flashcards",
    response_model=FlashcardSetResponse,
    summary="Get or generate flashcards for a paper",
)
async def get_flashcards(
    flashcard_service: FlashCardDep,
    opensearch: OpenSearchDep,
    db: SessionDep,
    paper_id: str = Path(
        ..., description="arXiv paper ID (e.g., '2401.00001' or '2401.00001v1')", regex=r"^\d{4}\.\d{4,5}(v\d+)?$"
    ),
    num_cards: int = Query(default=15, ge=5, le=50, description="Number of flashcards to generate"),
    topics: Optional[str] = Query(
        default=None, description="Comma-separated list of topics to focus on (e.g., 'Architecture,Methods')"
    ),
    force_refresh: bool = Query(default=False, description="Force regeneration even if cached flashcards exist"),
):
    """
    Get or generate study flashcards for a paper.

    Flow:
    1. Verify paper exists
    2. Retrieve chunks from OpenSearch
    3. Get/generate flashcards (checks cache → DB → LLM)
    4. Return flashcard set
    """
    paper_repo = PaperRepository(db)

    # 1. Verify paper exists
    paper = paper_repo.get_by_arxiv_id(paper_id)
    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper {paper_id} not found",
        )

    if not paper.pdf_processed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Paper {paper_id} not processed yet. Please wait for PDF processing to complete.",
        )

    logger.info(
        "Flashcard request received",
        extra={
            "paper_id": paper_id,
            "title": paper.title,
            "num_cards": num_cards,
            "force_refresh": force_refresh,
        },
    )

    # 2. Fetch chunks from OpenSearch
    try:
        chunks = opensearch.get_chunks_by_paper(paper_id)

        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No chunks found for paper {paper_id} — paper may not be fully indexed yet",
            )

        logger.info("Retrieved chunks from OpenSearch", extra={"paper_id": paper_id, "chunk_count": len(chunks)})

    except Exception as e:
        logger.error(f"Failed to retrieve chunks from OpenSearch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve paper content from search index"
        )

    # 3. Parse topics filter (if provided)
    topic_list = None
    if topics:
        topic_list = [t.strip() for t in topics.split(",") if t.strip()]
        logger.info(f"Filtering by topics: {topic_list}")

    # 4. Get/generate flashcards
    try:
        flashcard_set = await flashcard_service.get_or_generate(
            paper_id=str(paper.id),
            arxiv_id=paper.arxiv_id,
            paper_title=paper.title,
            paper_abstract=paper.abstract,
            chunks=chunks,
            num_cards=num_cards,
            topics=topic_list,
            force_refresh=force_refresh,
        )

    except FlashcardGenerationError as e:
        logger.error("Flashcard generation failed", extra={"paper_id": paper_id, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to generate flashcards: {str(e)}")

    # 5. Build response
    flashcard_responses = [
        FlashcardResponse(
            id=fc.id,
            paper_id=fc.paper_id,
            front=fc.front,
            back=fc.back,
            topic=fc.topic,
            difficulty=fc.difficulty,
            card_index=fc.card_index,
            generated_at=fc.generated_at,
        )
        for fc in flashcard_set.flashcards
    ]

    # Gather topics covered
    topics_covered = list(set(fc.topic for fc in flashcard_set.flashcards if fc.topic))

    # Check cache status
    cache_status = await flashcard_service.get_cache_status(str(paper.id))
    db_status = flashcard_service.get_db_status(str(paper.id))

    response = FlashcardSetResponse(
        paper_id=flashcard_set.paper_id,
        arxiv_id=flashcard_set.arxiv_id,
        paper_title=flashcard_set.paper_title,
        flashcards=flashcard_responses,
        meta={
            "total_cards": flashcard_set.total_cards,
            "generated_at": flashcard_set.generated_at.isoformat(),
            "expires_at": flashcard_set.expires_at.isoformat(),
            "is_fresh": db_status.get("is_fresh", True),
            "is_cached": cache_status.is_cached,
            "topics_covered": topics_covered,
            "model_used": flashcard_set.model_used,
        },
    )

    logger.info(
        "Flashcards returned successfully",
        extra={
            "paper_id": paper_id,
            "total_cards": len(flashcard_responses),
            "cached": cache_status.is_cached,
        },
    )

    return response


@router.post(
    "/{paper_id}/flashcards/regenerate",
    response_model=FlashcardSetResponse,
    summary="Force regenerate flashcards for a paper",
)
async def regenerate_flashcards(
    flashcard_service: FlashCardDep,
    opensearch: OpenSearchDep,
    db: SessionDep,
    paper_id: str = Path(..., description="arXiv paper ID", regex=r"^\d{4}\.\d{4,5}(v\d+)?$"),
    num_cards: int = Query(default=15, ge=5, le=50, description="Number of flashcards to generate"),
    topics: Optional[str] = Query(default=None, description="Comma-separated list of topics to focus on"),
):
    """
    Force regenerate flashcards for a paper.

    This endpoint explicitly regenerates flashcards, ignoring any cache.
    Useful when user wants fresh flashcards with improved quality.
    """
    logger.info("Explicit flashcard regeneration requested", extra={"paper_id": paper_id, "num_cards": num_cards})

    # Reuse main endpoint with force_refresh=True
    return await get_flashcards(
        flashcard_service=flashcard_service,
        opensearch=opensearch,
        db=db,
        paper_id=paper_id,
        num_cards=num_cards,
        topics=topics,
        force_refresh=True,
    )


@router.delete(
    "/{paper_id}/flashcards",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete flashcards for a paper",
)
async def delete_flashcards(
    paper_id: str,
    flashcard_service: FlashCardDep,
):
    """
    Delete flashcards from cache and database.

    Useful for cleanup or before regeneration.
    """
    await flashcard_service.invalidate(paper_id)

    logger.info("Flashcards deleted", extra={"paper_id": paper_id})


@router.get(
    "/{paper_id}/flashcards/status",
    summary="Get flashcard cache and database status",
)
async def get_flashcard_status(
    paper_id: str,
    flashcard_service: FlashCardDep,
):
    """
    Get status of flashcards for a paper.

    Returns information about:
    - Whether flashcards exist in cache (Redis)
    - Whether flashcards exist in DB
    - Freshness status
    - Cache TTL
    """
    # Check Redis cache status
    cache_status = await flashcard_service.get_cache_status(paper_id)

    # Check DB status
    db_status = flashcard_service.get_db_status(paper_id)

    return {
        "paper_id": paper_id,
        "cache": {
            "is_cached": cache_status.is_cached,
            "num_cards": cache_status.num_cards,
            "cached_at": cache_status.cached_at,
            "expires_at": cache_status.expires_at,
            "ttl_seconds": cache_status.ttl_seconds,
        },
        "database": {
            "exists": db_status.get("exists", False),
            "is_fresh": db_status.get("is_fresh", False),
            "total_cards": db_status.get("total_cards"),
            "generated_at": db_status.get("generated_at"),
            "expires_at": db_status.get("expires_at"),
        },
    }


@router.get(
    "/{paper_id}/flashcards/stats",
    summary="Get flashcard statistics",
)
async def get_flashcard_stats(
    paper_id: str,
    db: SessionDep,
):
    """
    Get statistics for a paper's flashcard set.

    Returns:
    - Total cards
    - Breakdown by topic
    - Breakdown by difficulty
    - Freshness info
    """
    from src.repositories.flashcards import FlashcardRepository

    repo = FlashcardRepository(session=db)

    # Get paper to validate arxiv_id
    paper_repo = PaperRepository(db)
    paper = paper_repo.get_by_arxiv_id(paper_id)

    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Paper {paper_id} not found")

    stats = repo.get_paper_stats(str(paper.id))

    if not stats.get("exists"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No flashcards found for this paper")

    return {
        "paper_id": paper_id,
        "total_cards": stats["total_cards"],
        "is_fresh": stats["is_fresh"],
        "generated_at": stats["generated_at"],
        "expires_at": stats["expires_at"],
        "model_used": stats["model_used"],
        "by_topic": stats["by_topic"],
        "by_difficulty": stats["by_difficulty"],
    }
