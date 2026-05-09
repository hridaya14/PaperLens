"""
Upload pipeline service.

Orchestrates the full lifecycle of a user-uploaded PDF:
  1. Save raw file to disk
  2. Parse with Docling
  3. Write Paper record to Postgres
  4. Index chunks into OpenSearch
  5. Write status updates to Redis throughout

This runs inside a FastAPI BackgroundTask so the HTTP response is
returned to the client before any of this work begins.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from redis.asyncio import Redis
from sqlalchemy.orm import Session
from src.models.paper import Paper
from src.schemas.api.upload import UploadMetadata, UploadStatus
from src.services.indexing.hybrid_indexer import HybridIndexingService
from src.services.pdf_parser.parser import PDFParserService

logger = logging.getLogger(__name__)

# How long (seconds) to keep task state in Redis.
# 24 hours is enough for any client to poll — after that, use paper_id directly.
TASK_TTL_SECONDS = 86_400

# Absolute path to the uploads directory inside the container.
# Using an absolute path ensures that pdf_url stored in Postgres is always
# resolvable regardless of the process working directory at serve time.
# The compose.yml api service mounts a named volume at this exact path so
# files survive container restarts.
UPLOAD_DIR = Path("/app/data/user_uploads")


# ---------------------------------------------------------------------------
# Redis task-state helpers
# ---------------------------------------------------------------------------


def _task_key(task_id: str) -> str:
    return f"upload_task:{task_id}"


async def _write_task_state(redis: Redis, task_id: str, state: Dict[str, Any]) -> None:
    """Serialise and write state dict to Redis with TTL."""
    await redis.set(_task_key(task_id), json.dumps(state, default=str), ex=TASK_TTL_SECONDS)


async def read_task_state(redis: Redis, task_id: str) -> Optional[Dict[str, Any]]:
    """Read raw task state dict from Redis. Returns None if task not found."""
    raw = await redis.get(_task_key(task_id))
    if raw is None:
        return None
    return json.loads(raw)


# ---------------------------------------------------------------------------
# File storage helpers
# ---------------------------------------------------------------------------


def save_upload_to_disk(file_bytes: bytes, upload_dir: Path) -> Path:
    """
    Persist uploaded bytes under a UUID filename.

    We deliberately ignore the original filename when writing to disk to
    avoid path-traversal issues and name collisions.  The original name is
    stored in Postgres (Paper.original_filename) for display purposes only.

    The returned path is always absolute (resolved) so that the value stored
    in ``Paper.pdf_url`` is unambiguous regardless of the process working
    directory at the time of the call.

    :param file_bytes: Raw PDF bytes from the multipart upload
    :param upload_dir: Directory to write into (created if missing)
    :returns: Absolute path to the saved file
    """
    # Resolve to absolute once — guards against relative paths being passed in.
    upload_dir = upload_dir.resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest = upload_dir / f"{uuid.uuid4()}.pdf"
    dest.write_bytes(file_bytes)
    logger.info(f"Saved upload to {dest} ({len(file_bytes):,} bytes)")
    return dest  # already absolute because upload_dir was resolved


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def run_upload_pipeline(
    *,
    task_id: str,
    file_bytes: bytes,
    original_filename: str,
    upload_dir: Path,
    metadata: UploadMetadata,
    # Injected services
    db: Session,
    redis: Redis,
    pdf_parser: PDFParserService,
    indexing_service: HybridIndexingService,
) -> None:
    """
    Full upload pipeline executed as a background task.

    Writes status updates to Redis at each stage so the polling endpoint
    can surface progress to the frontend.

    Stages and their Redis status values:
        pending     → set before this function is called (in the router)
        processing  → set at the start of this function
        completed   → set on success
        failed      → set on any unhandled exception
    """
    now = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------ #
    # Helper: update task state without losing existing fields            #
    # ------------------------------------------------------------------ #
    async def _update(patch: Dict[str, Any]) -> None:
        current = await read_task_state(redis, task_id) or {}
        current.update(patch)
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        await _write_task_state(redis, task_id, current)

    # ------------------------------------------------------------------ #
    # Mark as processing                                                  #
    # ------------------------------------------------------------------ #
    await _update({"status": UploadStatus.PROCESSING, "progress": {"step": "saving_file"}})

    try:
        # ---------------------------------------------------------------- #
        # Step 1: Save file to disk                                        #
        # ---------------------------------------------------------------- #
        pdf_path = save_upload_to_disk(file_bytes, upload_dir)
        await _update({"progress": {"step": "parsing_pdf"}})

        # ---------------------------------------------------------------- #
        # Step 2: Parse PDF with Docling                                   #
        # ---------------------------------------------------------------- #
        logger.info(f"[{task_id}] Parsing PDF: {pdf_path}")
        pdf_content = await pdf_parser.parse_pdf(pdf_path)

        # pdf_content can be None when the file passes the header check but
        # Docling can't extract usable text (e.g. image-only scans without OCR).
        # We still create the paper record — it just won't have raw_text.
        if pdf_content is None:
            logger.warning(f"[{task_id}] Docling returned no content — paper will have no raw text")

        await _update({"progress": {"step": "creating_db_record"}})

        # ---------------------------------------------------------------- #
        # Step 3: Build Paper ORM object and persist to Postgres           #
        # ---------------------------------------------------------------- #
        upload_time = datetime.now(timezone.utc)

        # Resolve title: prefer client-supplied, then extracted, then filename
        title = metadata.title or (pdf_content and _extract_title_from_content(pdf_content)) or original_filename

        authors = metadata.authors or []
        abstract = metadata.abstract or (pdf_content and pdf_content.raw_text[:500]) or ""
        categories = metadata.categories or []
        published_date = metadata.published_date or upload_time

        paper = Paper(
            source="user_upload",
            original_filename=original_filename,
            uploaded_at=upload_time,
            # arxiv_id intentionally omitted (NULL) for user uploads
            title=title,
            authors=authors,
            abstract=abstract,
            categories=categories,
            published_date=published_date,
            pdf_url=str(pdf_path),  # absolute path — safe to use directly at serve time
            # Parsed content
            raw_text=pdf_content.raw_text if pdf_content else None,
            sections=([s.model_dump() for s in pdf_content.sections] if pdf_content and pdf_content.sections else None),
            references=([r for r in pdf_content.references] if pdf_content and pdf_content.references else None),
            parser_used=pdf_content.parser_used.value if pdf_content else None,
            parser_metadata=pdf_content.metadata if pdf_content else None,
            pdf_processed=pdf_content is not None,
            pdf_processing_date=upload_time if pdf_content else None,
        )

        db.add(paper)
        db.commit()
        db.refresh(paper)

        logger.info(f"[{task_id}] Created Paper record: {paper.id}, pdf_url={paper.pdf_url}")
        await _update(
            {
                "paper_id": str(paper.id),
                "progress": {"step": "indexing", "chunks_done": 0},
            }
        )

        # ---------------------------------------------------------------- #
        # Step 4: Index into OpenSearch                                    #
        # ---------------------------------------------------------------- #
        # Build the dict that HybridIndexingService.index_paper() expects.
        # It was designed for ArXiv papers so it uses arxiv_id as the doc
        # identifier — see the patch in hybrid_indexer.py that falls back to
        # str(paper.id) when arxiv_id is absent.
        paper_data_for_indexer: Dict[str, Any] = {
            "id": str(paper.id),
            "arxiv_id": None,  # explicitly None — indexer handles this
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "categories": paper.categories,
            "published_date": paper.published_date.isoformat() if paper.published_date else None,
            "raw_text": paper.raw_text,
            "sections": paper.sections,
        }

        index_stats = await indexing_service.index_paper(paper_data_for_indexer)

        logger.info(f"[{task_id}] Indexing complete: {index_stats}")

        # ---------------------------------------------------------------- #
        # Step 5: Mark completed                                           #
        # ---------------------------------------------------------------- #
        await _update(
            {
                "status": UploadStatus.COMPLETED,
                "paper_id": str(paper.id),
                "progress": {
                    "step": "done",
                    "chunks_indexed": index_stats.get("chunks_indexed", 0),
                    "chunks_created": index_stats.get("chunks_created", 0),
                    "errors": index_stats.get("errors", 0),
                },
            }
        )

    except Exception as exc:
        logger.exception(f"[{task_id}] Upload pipeline failed: {exc}")
        await _update({"status": UploadStatus.FAILED, "error": str(exc)})
        raise  # re-raise so FastAPI logs the traceback


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_title_from_content(pdf_content: Any) -> Optional[str]:
    """
    Try to derive a title from the first section heading Docling found.

    Docling stores sections in order, so the very first one is usually
    the document title if it was detected as a heading.
    """
    if not pdf_content or not pdf_content.sections:
        return None
    first = pdf_content.sections[0]
    # PaperSection has a .title attribute
    candidate = getattr(first, "title", None)
    # Skip generic fallbacks that DoclingParser inserts
    if candidate and candidate.lower() not in ("content", "abstract", "introduction"):
        return candidate
    return None
