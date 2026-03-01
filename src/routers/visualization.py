import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Path, Query

from src.services.visualization.mindmaps.generator import MindMapGenerationError
from src.schemas.visualization.mindmaps import MindMap, MindMapCacheStatus
from src.repositories.paper import PaperRepository
from src.services.opensearch.client import OpenSearchClient
from src.dependencies import OpenSearchDep, MindMapDep, SessionDep
from src.repositories.paper import PaperRepository


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/visualization", tags=["mindmap"])


@router.get(
    "/{paper_id}/mindmap",
    response_model=MindMap,
    summary="Get or generate a mind map for a paper",
)
async def get_mindmap(
    mindmap_service: MindMapDep,
    opensearch: OpenSearchDep ,
    db: SessionDep,
    paper_id: str = Path(
        ..., description="arXiv paper ID (e.g., '2401.00001' or '2401.00001v1')", regex=r"^\d{4}\.\d{4,5}(v\d+)?$"),
 
):
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
    await mindmap_service.invalidate(str(paper_id))
