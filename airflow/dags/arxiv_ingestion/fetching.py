"""
Fetching tasks for the arXiv ingestion DAG.

Original fetch_daily_papers() has been split into two tasks to allow
the filter stack to run between metadata fetch and PDF processing:

  fetch_metadata_only  — arXiv API call only, no PDFs, pushes paper list to XCom
  process_pdfs         — downloads + parses PDFs for papers that passed filtering,
                         updates DB records with full content

fetch_daily_papers() is preserved for backward compatibility but is no
longer used by the main DAG.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from src.schemas.arxiv.paper import ArxivPaper

from .common import get_cached_services

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task 1 — Metadata fetch (arXiv API only, no PDFs)
# ---------------------------------------------------------------------------


def fetch_metadata_only(**context) -> dict:
    """Fetch paper metadata from arXiv for the target date (or backfill range).

    Normal daily run: fetches yesterday's papers.
    Backfill run: set ``backfill_from_date`` (and optionally ``backfill_to_date``)
    in the DAG trigger params to fetch a custom date range.

    DAG params:
      backfill_from_date   — YYYYMMDD start (default: yesterday)
      backfill_to_date     — YYYYMMDD end   (default: same as from_date)
      max_results_override — override max_results for this run (0 = client default)

    XCom pushed:
      key="papers"       → list of ArxivPaper dicts
      key="fetch_date"   → from_date string (YYYYMMDD)
      key="to_date"      → to_date string (YYYYMMDD)
      key="papers_count" → number of papers fetched
    """
    logger.info("Starting metadata fetch task")

    arxiv_client, _, _, _, _ = get_cached_services()

    # ----------------------------------------------------------------
    # Resolve date range — params take priority over execution_date
    # ----------------------------------------------------------------
    params = context.get("params") or {}
    backfill_from = (params.get("backfill_from_date") or "").strip()
    backfill_to   = (params.get("backfill_to_date")   or "").strip()
    max_results_override = int(params.get("max_results_override") or 0)

    if backfill_from:
        from_date = backfill_from
        to_date   = backfill_to or backfill_from  # default to same day
        logger.info(f"Backfill mode: fetching arXiv papers from {from_date} to {to_date}")
    else:
        # Normal daily run — yesterday relative to execution_date
        execution_date = context.get("execution_date")
        if execution_date:
            yesterday = (execution_date - timedelta(days=1)).strftime("%Y%m%d")
        else:
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        from_date = to_date = yesterday
        logger.info(f"Daily mode: fetching arXiv papers for {from_date}")

    max_results = max_results_override if max_results_override > 0 else arxiv_client.max_results
    logger.info(f"max_results={max_results}, date range={from_date}→{to_date}")

    papers: List[ArxivPaper] = asyncio.run(
        arxiv_client.fetch_papers(
            max_results=max_results,
            from_date=from_date,
            to_date=to_date,
            sort_by="submittedDate",
            sort_order="descending",
        )
    )

    logger.info(f"Fetched {len(papers)} papers from arXiv ({from_date}→{to_date})")

    papers_data = [p.model_dump() for p in papers]

    ti = context.get("ti")
    if ti:
        ti.xcom_push(key="papers",       value=papers_data)
        ti.xcom_push(key="fetch_date",   value=from_date)
        ti.xcom_push(key="to_date",      value=to_date)
        ti.xcom_push(key="papers_count", value=len(papers))

    return {"papers_fetched": len(papers), "from_date": from_date, "to_date": to_date}



# ---------------------------------------------------------------------------
# Task 2 — PDF processing (runs after filter, only on ingested papers)
# ---------------------------------------------------------------------------


async def _run_pdf_processing(ingested_papers_data: List[dict]) -> dict:
    """Async inner function for PDF download + parse + DB update.

    :param ingested_papers_data: Serialised ArxivPaper dicts from XCom
    :returns: Statistics dict
    """
    from src.repositories.paper import PaperRepository

    _, _, database, metadata_fetcher, _ = get_cached_services()

    if not ingested_papers_data:
        logger.info("No ingested papers to process PDFs for")
        return {"pdfs_downloaded": 0, "pdfs_parsed": 0, "errors": []}

    # Deserialise back to ArxivPaper objects
    papers = [ArxivPaper(**p) for p in ingested_papers_data]

    logger.info(f"Starting PDF processing for {len(papers)} ingested papers")

    # Download + parse PDFs using existing pipeline
    pdf_results = await metadata_fetcher._process_pdfs_batch(papers)

    # Update DB records with parsed content
    with database.get_session() as session:
        paper_repo = PaperRepository(session)

        for paper in papers:
            parsed_paper = pdf_results.get("parsed_papers", {}).get(paper.arxiv_id)
            if not parsed_paper:
                continue

            existing = paper_repo.get_by_arxiv_id(paper.arxiv_id)
            if not existing:
                logger.warning(f"Paper {paper.arxiv_id} not found in DB during PDF update — was it stored in the filter task?")
                continue

            # Serialise parsed content onto the existing record
            parsed_content = metadata_fetcher._serialize_parsed_content(parsed_paper)

            for key, value in parsed_content.items():
                setattr(existing, key, value)

            paper_repo.update(existing)
            logger.debug(f"Updated {paper.arxiv_id} with PDF content")

        try:
            session.commit()
        except Exception as e:
            logger.error(f"Failed to commit PDF content updates: {e}")
            session.rollback()
            raise

    return {
        "pdfs_downloaded": pdf_results["downloaded"],
        "pdfs_parsed": pdf_results["parsed"],
        "errors": pdf_results["errors"],
    }


def process_pdfs(**context) -> dict:
    """Download and parse PDFs for papers that passed the filter.

    Pulls the ingested paper list from XCom (written by filter_and_store_metadata).
    Updates existing DB records with full PDF content.

    XCom consumed:
      task_id="filter_and_store_metadata", key="ingested_papers"

    XCom pushed:
      key="pdf_results" → {"pdfs_downloaded": N, "pdfs_parsed": N, "errors": [...]}
    """
    logger.info("Starting PDF processing task")

    ti = context.get("ti")
    ingested_papers_data = []

    if ti:
        ingested_papers_data = (
            ti.xcom_pull(
                task_ids="filter_papers",
                key="ingested_papers",
            )
            or []
        )

    if not ingested_papers_data:
        logger.info("No ingested papers received from filter task — skipping PDF processing")
        return {"pdfs_downloaded": 0, "pdfs_parsed": 0, "errors": []}

    logger.info(f"Processing PDFs for {len(ingested_papers_data)} ingested papers")

    results = asyncio.run(_run_pdf_processing(ingested_papers_data))

    logger.info(
        f"PDF processing complete: {results['pdfs_downloaded']} downloaded, "
        f"{results['pdfs_parsed']} parsed, {len(results['errors'])} errors"
    )

    if ti:
        ti.xcom_push(
            key="pdf_results",
            value={
                "pdfs_downloaded": results["pdfs_downloaded"],
                "pdfs_parsed": results["pdfs_parsed"],
                "error_count": len(results["errors"]),
            },
        )

    return results


# ---------------------------------------------------------------------------
# Legacy — preserved for backward compatibility, not used by main DAG
# ---------------------------------------------------------------------------


async def run_paper_ingestion_pipeline(
    target_date: str,
    process_pdfs: bool = True,
) -> dict:
    """Original single-shot pipeline. Preserved but not used by main DAG."""
    arxiv_client, _, database, metadata_fetcher, _ = get_cached_services()
    max_results = arxiv_client.max_results
    logger.info(f"Using default max_results from config: {max_results}")
    with database.get_session() as session:
        return await metadata_fetcher.fetch_and_process_papers(
            max_results=max_results,
            from_date=target_date,
            to_date=target_date,
            process_pdfs=process_pdfs,
            store_to_db=True,
            db_session=session,
        )


def fetch_daily_papers(**context) -> dict:
    """Original combined fetch+store task. Preserved but not used by main DAG."""
    logger.info("Starting daily paper fetching task (legacy)")
    execution_date = context.get("execution_date")
    if execution_date:
        target_date = (execution_date - timedelta(days=1)).strftime("%Y%m%d")
    else:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    results = asyncio.run(run_paper_ingestion_pipeline(target_date=target_date, process_pdfs=True))
    results["date"] = target_date

    ti = context.get("ti")
    if ti:
        ti.xcom_push(key="fetch_results", value=results)
    return results
