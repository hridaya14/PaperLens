"""
Upload router.

Endpoints:
  POST /uploads/paper              — accept a PDF, kick off background processing
  GET  /uploads/{task_id}/status   — poll background task progress
  GET  /uploads/{paper_id}/detail  — fetch full paper once completed
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from src.dependencies import (
    EmbeddingsDep,
    OpenSearchDep,
    PDFParserDep,
    RedisDep,
    SessionDep,
)
from src.repositories.paper import PaperRepository
from src.schemas.api.upload import (
    UploadAcceptedResponse,
    UploadedPaperResponse,
    UploadMetadata,
    UploadStatus,
    UploadStatusResponse,
)
from src.services.indexing.factory import make_hybrid_indexing_service
from src.services.paper_upload_pipeline import (
    TASK_TTL_SECONDS,
    UPLOAD_DIR,
    _write_task_state,
    read_task_state,
    run_upload_pipeline,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["uploads"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB — matches PDFParserSettings
ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/paper",
    response_model=UploadAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a PDF paper for ingestion",
    description=(
        "Accepts a PDF file and optional metadata. Processing (parsing, embedding, "
        "indexing) happens in the background. Poll GET /uploads/{task_id}/status "
        "to track progress."
    ),
)
async def upload_paper(
    background_tasks: BackgroundTasks,
    db: SessionDep,
    redis: RedisDep,
    pdf_parser: PDFParserDep,
    embeddings_service: EmbeddingsDep,
    opensearch: OpenSearchDep,
    # ---- multipart fields ----
    file: UploadFile = File(..., description="PDF file to upload"),
    # Optional metadata as a JSON string in the multipart body.
    # Using a JSON string (not nested form fields) keeps the multipart
    # request simple and is easy to construct from the Next.js frontend.
    metadata_json: Optional[str] = Form(
        None,
        alias="metadata",
        description='Optional JSON string, e.g. {"title": "My Paper", "authors": ["Alice"]}',
    ),
) -> UploadAcceptedResponse:
    """
    Accept a PDF upload and queue background processing.

    Validation happens synchronously (before 202 is returned) so the client
    gets immediate feedback on bad files rather than discovering failure later
    during polling.
    """

    # ------------------------------------------------------------------ #
    # 1. Validate content type                                            #
    # ------------------------------------------------------------------ #
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        # Also accept if content_type is missing but filename ends with .pdf
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Only PDF files are accepted. Got content-type: '{file.content_type}'",
            )

    # ------------------------------------------------------------------ #
    # 2. Read file bytes + size check                                     #
    # ------------------------------------------------------------------ #
    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {MAX_UPLOAD_SIZE_BYTES // 1024 // 1024} MB.",
        )

    # ------------------------------------------------------------------ #
    # 3. Validate PDF magic bytes (quick check before touching disk)      #
    # ------------------------------------------------------------------ #
    if not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File does not appear to be a valid PDF (missing PDF header).",
        )

    # ------------------------------------------------------------------ #
    # 4. Parse optional metadata                                          #
    # ------------------------------------------------------------------ #
    metadata = UploadMetadata()
    if metadata_json:
        try:
            metadata = UploadMetadata.model_validate_json(metadata_json)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid metadata JSON: {exc}",
            )

    # ------------------------------------------------------------------ #
    # 5. Create task record in Redis (status = pending)                   #
    # ------------------------------------------------------------------ #
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    initial_state = {
        "task_id": task_id,
        "status": UploadStatus.PENDING,
        "original_filename": file.filename,
        "paper_id": None,
        "progress": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    await _write_task_state(redis, task_id, initial_state)

    # ------------------------------------------------------------------ #
    # 6. Build the indexing service                                       #
    # This constructs a fresh HybridIndexingService with its own          #
    # OpenSearch + embeddings connections, matching exactly how the       #
    # Airflow DAG creates it via make_hybrid_indexing_service().          #
    # ------------------------------------------------------------------ #
    indexing_service = make_hybrid_indexing_service()

    # ------------------------------------------------------------------ #
    # 7. Queue background task                                            #
    # ------------------------------------------------------------------ #
    background_tasks.add_task(
        run_upload_pipeline,
        task_id=task_id,
        file_bytes=file_bytes,
        original_filename=file.filename or "unknown.pdf",
        upload_dir=UPLOAD_DIR,
        metadata=metadata,
        db=db,
        redis=redis,
        pdf_parser=pdf_parser,
        indexing_service=indexing_service,
    )

    logger.info(f"Upload accepted: task_id={task_id}, file='{file.filename}', size={len(file_bytes):,} bytes")

    return UploadAcceptedResponse(task_id=task_id)


@router.get(
    "/{task_id}/status",
    response_model=UploadStatusResponse,
    summary="Poll upload task status",
    description="Returns current processing status. Poll until status is 'completed' or 'failed'.",
)
async def get_upload_status(
    task_id: str,
    redis: RedisDep,
) -> UploadStatusResponse:
    """Return the current status of an upload background task."""
    state = await read_task_state(redis, task_id)

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found. It may have expired (tasks are kept for 24 hours).",
        )

    return UploadStatusResponse(
        task_id=state["task_id"],
        status=UploadStatus(state["status"]),
        paper_id=state.get("paper_id"),
        original_filename=state.get("original_filename"),
        progress=state.get("progress"),
        error=state.get("error"),
        created_at=datetime.fromisoformat(state["created_at"]),
        updated_at=datetime.fromisoformat(state["updated_at"]),
    )


@router.get(
    "/{paper_id}/detail",
    response_model=UploadedPaperResponse,
    summary="Get full detail of an uploaded paper",
    description="Fetch the complete Paper record for a successfully uploaded paper.",
)
def get_uploaded_paper(
    paper_id: str,
    db: SessionDep,
) -> UploadedPaperResponse:
    """
    Return full paper detail for a completed upload.

    Uses the paper_id returned by the status endpoint once
    status == 'completed'.
    """
    repo = PaperRepository(db)

    try:
        paper_uuid = uuid.UUID(paper_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{paper_id}' is not a valid UUID.",
        )

    paper = repo.get_by_id(paper_uuid)

    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper '{paper_id}' not found.",
        )

    if paper.source != "user_upload":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint is only for user-uploaded papers. Use /papers/{arxiv_id} for ArXiv papers.",
        )

    return UploadedPaperResponse.model_validate(paper)


@router.delete(
    "/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an uploaded paper",
    description=(
        "Deletes the paper from Postgres, removes all its chunks from OpenSearch, "
        "and deletes the PDF file from disk. Only works for user-uploaded papers."
    ),
)
def delete_uploaded_paper(
    paper_id: str,
    db: SessionDep,
    opensearch: OpenSearchDep,
) -> None:
    # ---- 1. Resolve and validate ----
    try:
        paper_uuid = uuid.UUID(paper_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{paper_id}' is not a valid UUID.",
        )

    repo = PaperRepository(db)
    paper = repo.get_by_id(paper_uuid)

    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper '{paper_id}' not found.",
        )

    if paper.source != "user_upload":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only user-uploaded papers can be deleted through this endpoint.",
        )

    # ---- 2. Delete OpenSearch chunks ----
    # Chunks were indexed with str(paper.id) in the arxiv_id field
    # (see hybrid_indexer.py — doc_identifier = arxiv_id or paper_id).
    opensearch.delete_paper_chunks(str(paper.id))

    # ---- 3. Delete file from disk ----
    if paper.pdf_url:
        pdf_path = Path(paper.pdf_url)
        if pdf_path.exists():
            try:
                pdf_path.unlink()
                logger.info(f"Deleted PDF file: {pdf_path}")
            except OSError as exc:
                # Log but don't abort — the DB record and index are more important
                # to clean up. A stale file on disk is recoverable manually.
                logger.warning(f"Could not delete PDF file {pdf_path}: {exc}")

    # ---- 4. Delete Postgres record ----
    repo.delete(paper)

    logger.info(f"Deleted user upload: paper_id={paper_id}")
    # 204 No Content — FastAPI returns empty body automatically
