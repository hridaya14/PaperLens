"""
Visualization API router - Mind Maps and Flashcards.

Unified endpoints for paper visualizations and study tools.
Supports both arXiv-ingested papers (identified by arXiv ID) and
user-uploaded papers (identified by UUID).

Location: src/routers/visualization.py
"""

import logging
import re
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Compiled once at import time for speed.
_ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")


def _resolve_paper(paper_ref: str, db: Session):
    """Resolve *paper_ref* to a Paper ORM object or raise HTTP 404.

    Accepts either:
    - An arXiv ID  (e.g. ``"2401.00001"`` or ``"2401.00001v2"``)
    - A UUID string (e.g. ``"3fa85f64-5717-4562-b3fc-2c963f66afa6"``)

    Raises:
        HTTPException(404): If no paper is found for the given reference.
    """
    paper_repo = PaperRepository(db)
    paper = paper_repo.get_by_id_or_arxiv_id(paper_ref)
    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper '{paper_ref}' not found. Provide a valid arXiv ID (e.g. '2401.00001') or paper UUID.",
        )
    return paper


def _get_chunks(opensearch: OpenSearchClient, paper):
    """Fetch OpenSearch chunks for *paper*, routing by paper type.

    arXiv papers are indexed under the ``arxiv_id`` field.
    User-uploaded papers have no ``arxiv_id`` and are indexed under ``paper_id`` (UUID).
    """
    return opensearch.get_chunks_for_paper(
        paper_uuid=str(paper.id),
        arxiv_id=paper.arxiv_id or None,
    )


# ---------------------------------------------------------------------------
# Mind Map Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{paper_id}/mindmap",
    response_model=MindMap,
    summary="Get or generate a mind map for a paper",
    description=("Accepts either an arXiv ID (e.g. `2401.00001`) or a paper UUID for user-uploaded documents."),
)
async def get_mindmap(
    mindmap_service: MindMapDep,
    opensearch: OpenSearchDep,
    db: SessionDep,
    paper_id: str = Path(
        ...,
        description="arXiv paper ID (e.g. '2401.00001') or paper UUID for user uploads",
    ),
):
    """Get or generate mind map for a paper."""
    # 1. Resolve paper (arXiv ID or UUID)
    paper = _resolve_paper(paper_id, db)

    # 2. Fetch chunks — routing handled transparently
    chunks = _get_chunks(opensearch, paper)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No chunks found for paper '{paper_id}' — paper may not be fully indexed yet",
        )

    # 3. Get or generate mind map
    try:
        mindmap = await mindmap_service.get_or_generate(
            paper_id=str(paper.id),
            arxiv_id=paper.arxiv_id,  # May be None for user uploads — service should handle this
            paper_title=paper.title,
            chunks=chunks,
        )
    except MindMapGenerationError as e:
        logger.error("Mind map generation failed", extra={"paper_id": paper_id, "error": str(e)})
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
    db: SessionDep,
):
    """Check mind map cache status.

    Resolves the paper so that the cache is always keyed on the internal UUID,
    ensuring consistent behaviour regardless of whether an arXiv ID or UUID was supplied.
    """
    paper = _resolve_paper(paper_id, db)
    return await mindmap_service.get_cache_status(str(paper.id))


@router.delete(
    "/{paper_id}/mindmap",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate cached mind map for a paper",
)
async def invalidate_mindmap(
    paper_id: str,
    mindmap_service: MindMapDep,
    db: SessionDep,
):
    """Delete mind map from cache."""
    paper = _resolve_paper(paper_id, db)
    await mindmap_service.invalidate(str(paper.id))


# ---------------------------------------------------------------------------
# Flashcard Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{paper_id}/flashcards",
    response_model=FlashcardSetResponse,
    summary="Get or generate flashcards for a paper",
    description=("Accepts either an arXiv ID (e.g. `2401.00001`) or a paper UUID for user-uploaded documents."),
)
async def get_flashcards(
    flashcard_service: FlashCardDep,
    opensearch: OpenSearchDep,
    db: SessionDep,
    paper_id: str = Path(
        ...,
        description="arXiv paper ID (e.g. '2401.00001') or paper UUID for user uploads",
    ),
    num_cards: int = Query(default=15, ge=5, le=50, description="Number of flashcards to generate"),
    topics: Optional[str] = Query(
        default=None,
        description="Comma-separated list of topics to focus on (e.g. 'Architecture,Methods')",
    ),
    force_refresh: bool = Query(default=False, description="Force regeneration even if cached flashcards exist"),
):
    """Get or generate study flashcards for a paper.

    Flow:
    1. Resolve paper by arXiv ID or UUID.
    2. Verify PDF is processed.
    3. Retrieve chunks from OpenSearch (routing by paper type).
    4. Get/generate flashcards (checks cache → DB → LLM).
    5. Return flashcard set.
    """
    # 1. Resolve paper
    paper = _resolve_paper(paper_id, db)

    if not paper.pdf_processed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Paper '{paper_id}' not processed yet. Please wait for PDF processing to complete.",
        )

    logger.info(
        "Flashcard request received",
        extra={
            "paper_id": paper_id,
            "resolved_uuid": str(paper.id),
            "title": paper.title,
            "num_cards": num_cards,
            "force_refresh": force_refresh,
            "source": "arxiv" if paper.arxiv_id else "user_upload",
        },
    )

    # 2. Fetch chunks — routing handled transparently
    try:
        chunks = _get_chunks(opensearch, paper)

        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No chunks found for paper '{paper_id}' — paper may not be fully indexed yet",
            )

        logger.info("Retrieved chunks from OpenSearch", extra={"paper_id": paper_id, "chunk_count": len(chunks)})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve chunks from OpenSearch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve paper content from search index",
        )

    # 3. Parse topics filter
    topic_list = None
    if topics:
        topic_list = [t.strip() for t in topics.split(",") if t.strip()]
        logger.info(f"Filtering by topics: {topic_list}")

    # 4. Get/generate flashcards (always keyed on internal UUID)
    try:
        flashcard_set = await flashcard_service.get_or_generate(
            paper_id=str(paper.id),
            arxiv_id=paper.arxiv_id,  # May be None for user uploads
            paper_title=paper.title,
            paper_abstract=paper.abstract,
            chunks=chunks,
            num_cards=num_cards,
            topics=topic_list,
            force_refresh=force_refresh,
        )

    except FlashcardGenerationError as e:
        logger.error("Flashcard generation failed", extra={"paper_id": paper_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate flashcards: {str(e)}",
        )

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

    topics_covered = list(set(fc.topic for fc in flashcard_set.flashcards if fc.topic))

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
    paper_id: str = Path(
        ...,
        description="arXiv paper ID (e.g. '2401.00001') or paper UUID for user uploads",
    ),
    num_cards: int = Query(default=15, ge=5, le=50, description="Number of flashcards to generate"),
    topics: Optional[str] = Query(default=None, description="Comma-separated list of topics to focus on"),
):
    """Force regenerate flashcards for a paper, ignoring any cache."""
    logger.info("Explicit flashcard regeneration requested", extra={"paper_id": paper_id, "num_cards": num_cards})

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
    db: SessionDep,
):
    """Delete flashcards from cache and database."""
    paper = _resolve_paper(paper_id, db)
    await flashcard_service.invalidate(str(paper.id))
    logger.info("Flashcards deleted", extra={"paper_id": paper_id, "resolved_uuid": str(paper.id)})


@router.get(
    "/{paper_id}/flashcards/status",
    summary="Get flashcard cache and database status",
)
async def get_flashcard_status(
    paper_id: str,
    flashcard_service: FlashCardDep,
    db: SessionDep,
):
    """Get status of flashcards for a paper (Redis cache + DB)."""
    paper = _resolve_paper(paper_id, db)
    internal_id = str(paper.id)

    cache_status = await flashcard_service.get_cache_status(internal_id)
    db_status = flashcard_service.get_db_status(internal_id)

    return {
        "paper_id": paper_id,
        "resolved_uuid": internal_id,
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
    """Get topic/difficulty breakdown for a paper's flashcard set."""
    from src.repositories.flashcards import FlashcardRepository

    paper = _resolve_paper(paper_id, db)
    internal_id = str(paper.id)

    repo = FlashcardRepository(session=db)
    stats = repo.get_paper_stats(internal_id)

    if not stats.get("exists"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No flashcards found for this paper",
        )

    return {
        "paper_id": paper_id,
        "resolved_uuid": internal_id,
        "total_cards": stats["total_cards"],
        "is_fresh": stats["is_fresh"],
        "generated_at": stats["generated_at"],
        "expires_at": stats["expires_at"],
        "model_used": stats["model_used"],
        "by_topic": stats["by_topic"],
        "by_difficulty": stats["by_difficulty"],
    }
