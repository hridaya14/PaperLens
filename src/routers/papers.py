from datetime import datetime
from typing import List, Optional
import logging
import uuid as uuid_lib
import pathlib

from fastapi import APIRouter, HTTPException, Path, Query, status
from fastapi.responses import FileResponse

from src.dependencies import OpenSearchDep, SessionDep
from src.repositories.paper import PaperRepository
from src.schemas.arxiv.paper import PaperResponse, PaperSearchFilters, PaperSearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("/", response_model=PaperSearchResponse)
def list_papers(
    db: SessionDep,
    limit: int = Query(default=10, ge=1, le=100, description="Number of papers to return (1-100)"),
    offset: int = Query(default=0, ge=0, description="Number of papers to skip"),
) -> PaperSearchResponse:
    """Get a list of papers with pagination."""
    paper_repo = PaperRepository(db)
    papers = paper_repo.get_all(limit=limit, offset=offset)
    total = paper_repo.get_count()
    return PaperSearchResponse(papers=[PaperResponse.model_validate(paper) for paper in papers], total=total)


@router.get("/search")
def search_papers(
    db: SessionDep,
    q: Optional[str] = None,
    categories: Optional[List[str]] = Query(None),
    pdf_processed: Optional[bool] = None,
    published_after: Optional[datetime] = None,
    published_before: Optional[datetime] = None,
    source: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> PaperSearchResponse:
    filters = PaperSearchFilters(
        query=q,
        categories=categories,
        pdf_processed=pdf_processed,
        published_after=published_after,
        published_before=published_before,
        source=source,
    )
    repo = PaperRepository(db)
    papers, total = repo.search(filters, limit, offset)
    return PaperSearchResponse(
        papers=[PaperResponse.model_validate(paper) for paper in papers],
        total=total,
    )


@router.get("/{arxiv_id}", response_model=PaperResponse)
def get_paper_details(
    db: SessionDep,
    arxiv_id: str = Path(
        ...,
        description="arXiv paper ID (e.g., '2401.00001' or '2401.00001v1')",
        regex=r"^\d{4}\.\d{4,5}(v\d+)?$",
    ),
) -> PaperResponse:
    """Get details of a specific paper by arXiv ID."""
    paper_repo = PaperRepository(db)
    paper = paper_repo.get_by_arxiv_id(arxiv_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return PaperResponse.model_validate(paper)

@router.get(
    "/{paper_id}/pdf",
    summary="Serve the PDF file for an uploaded paper",
    response_class=FileResponse,
)
def serve_uploaded_pdf(paper_id: str, db: SessionDep) -> FileResponse:
    try:
        paper_uuid = uuid.UUID(paper_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{paper_id}' is not a valid UUID.")

    repo = PaperRepository(db)
    paper = repo.get_by_id(paper_uuid)

    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Paper '{paper_id}' not found.")

    if paper.source != "user_upload":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only user-uploaded PDFs can be served this way.")

    if not paper.pdf_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No PDF file associated with this paper.")

    pdf_path = pathlib.Path(paper.pdf_url)
    if not pdf_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF file not found on disk.")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=paper.original_filename or f"{paper_id}.pdf",
    )


@router.delete(
    "/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a paper",
    description=(
        "Deletes any paper by its internal UUID. Adapts cleanup based on source: "
        "arxiv papers have their OpenSearch chunks removed; "
        "user uploads additionally have their PDF file deleted from disk. "
        "The paper is also removed from any projects it belongs to (cascade)."
    ),
)
def delete_paper(
    paper_id: str,
    db: SessionDep,
    opensearch: OpenSearchDep,
) -> None:
    try:
        paper_uuid = uuid_lib.UUID(paper_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{paper_id}' is not a valid paper ID. Use the UUID `id` field from any paper response.",
        )

    repo = PaperRepository(db)
    paper = repo.get_by_id(paper_uuid)

    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper '{paper_id}' not found.",
        )

    # ---- Delete OpenSearch chunks ----
    doc_identifier = paper.arxiv_id if paper.arxiv_id else str(paper.id)
    opensearch.delete_paper_chunks(doc_identifier)

    # ---- Delete PDF file from disk (user uploads only) ----
    if paper.source == "user_upload" and paper.pdf_url:
        pdf_path = pathlib.Path(paper.pdf_url)
        if pdf_path.exists():
            try:
                pdf_path.unlink()
            except OSError as exc:
                logger.warning(f"Could not delete PDF file {pdf_path}: {exc}")

    # ---- Delete Postgres record ----
    repo.delete(paper)

    logger.info(f"Deleted paper: id={paper_id}, source={paper.source}")
