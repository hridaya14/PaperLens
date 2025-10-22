import asyncio
import logging
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Tuple, Optional

# Add project root to Python path for imports
sys.path.insert(0, "/opt/airflow")

# All imports at the top
from sqlalchemy import text
from src.db.factory import make_database
from src.repositories.paper import PaperRepository
from src.services.arxiv.factory import make_arxiv_client
from src.services.metadata_fetcher import make_metadata_fetcher
from src.services.opensearch.factory import make_opensearch_client
from src.services.pdf_parser.factory import make_pdf_parser_service

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_cached_services() -> Tuple[Any, Any, Any, Any]:
    """Get cached service instances using lru_cache for automatic memoization.

    :returns: Tuple of (arxiv_client, pdf_parser, database, metadata_fetcher, opensearch_client)
    """
    logger.info("Initializing services (cached with lru_cache)")

    # Initialize core services
    arxiv_client = make_arxiv_client()
    pdf_parser = make_pdf_parser_service()
    database = make_database()
    opensearch_client = make_opensearch_client()

    # Create metadata fetcher with dependencies
    metadata_fetcher = make_metadata_fetcher(arxiv_client, pdf_parser, opensearch_client)

    logger.info("All services initialized and cached with lru_cache")
    return arxiv_client, pdf_parser, database, metadata_fetcher, opensearch_client


async def run_paper_ingestion_pipeline(
    target_date: str,
    max_results: int = 5,
    process_pdfs: bool = True,
    index_to_opensearch: bool = True,
) -> dict:
    """
    Async wrapper for the paper ingestion pipeline.

    Args:
        target_date: Date to fetch papers for (YYYYMMDD format)
        max_results: Maximum number of papers to fetch
        process_pdfs: Whether to process PDFs
        index_to_opensearch: Whether to index papers to Opensearch

    Returns:
        Dictionary with processing results
    """
    arxiv_client, _pdf_parser, database, metadata_fetcher, _opensearch_client = get_cached_services()

    if max_results is None:
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
            index_to_opensearch=index_to_opensearch,
        )

def setup_environment():
    """Setup environment and verify dependencies."""
    logger.info("Setting up environment for arXiv paper ingestion")

    try:
        # Get cached services (initialized once)
        arxiv_client, _pdf_parser, database, _metadata_fetcher, opensearch_client = get_cached_services()

        # Test database connection
        with database.get_session() as session:
            session.execute(text("SELECT 1"))
            logger.info("Database connection verified")
        
        # Test Opensearch Connection
        if opensearch_client.health_check():
            logger.info("OpenSearch connection verified")
            # Ensure index exists
            if opensearch_client.create_index(force=False):
                logger.info("OpenSearch index created")
            else:
                logger.info("OpenSearch index already exists")
        else:
            logger.warning("OpenSearch not healthy, indexing will be skipped")

        logger.info(f"arXiv client ready: {arxiv_client.base_url}")
        logger.info("PDF parser service ready (Docling models cached)")

        return {"status": "success", "message": "Environment setup completed"}

    except Exception as e:
        error_msg = f"Environment setup failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def fetch_daily_papers(**context):
    """
    Fetch papers from the last 24 hours.

    This function:
    1. Calculates the date range for yesterday
    2. Fetches papers using the MetadataFetcher
    3. Returns processing statistics
    """
    logger.info("Starting daily arXiv paper fetch")

    try:
        # Calculate date range (yesterday - execution_date - 1)
        execution_date = context["ds"]  # YYYY-MM-DD format
        execution_dt = datetime.strptime(execution_date, "%Y-%m-%d")
        target_dt = execution_dt - timedelta(days=1)  # Get papers from day before
        target_date = target_dt.strftime("%Y%m%d")

        logger.info(f"Fetching papers for date: {target_date}")

        # Execute paper ingestion pipeline
        results = asyncio.run(
            run_paper_ingestion_pipeline(
                target_date=target_date,
                max_results=None,
                process_pdfs=True,
                index_to_opensearch=False,
            )
        )
        logger.info(f"Daily paper fetch completed: {results}")

        if results.get("papers_fetched", 0) == 0:
            logger.warning(f"No papers found for date {target_date}")

        # Store results for downstream tasks
        context["task_instance"].xcom_push(key="fetch_results", value=results)

        return results

    except Exception as e:
        error_msg = f"Daily paper fetch failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def process_failed_pdfs(**context):
    """
    Retry processing of PDFs that failed in the main fetch task.

    This function:
    1. Gets failed PDF list from the main task
    2. Retries processing with different settings
    3. Reports final success/failure statistics
    """
    logger.info("Processing failed PDFs")

    try:
        fetch_results = context["task_instance"].xcom_pull(task_ids="fetch_daily_papers", key="fetch_results")

        if not fetch_results or not fetch_results.get("errors"):
            logger.info("No failed PDFs to retry")
            return {"status": "skipped", "message": "No failures to retry"}

        logger.info(f"Found {len(fetch_results['errors'])} errors to investigate")

        for error in fetch_results["errors"]:
            # TODO: Implement retry logic
            logger.warning(f"Error to investigate: {error}")

        return {
            "status": "analyzed",
            "errors_logged": len(fetch_results["errors"]),
            "message": "Errors logged for investigation",
        }

    except Exception as e:
        error_msg = f"Failed PDF processing error: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def index_papers_to_opensearch(**context):
    """Index stored papers from PostgreSQL to OpenSearch.

    This is the single dedicated task for OpenSearch indexing to avoid duplication.
    It reads papers stored by fetch_daily_papers and indexes them to OpenSearch.
    """
    logger.info("Starting OpenSearch indexing (Week 3 - Dedicated Task)")

    try:
        fetch_results = context["task_instance"].xcom_pull(task_ids="fetch_daily_papers", key="fetch_results")

        if not fetch_results:
            logger.warning("No fetch results available for OpenSearch indexing")
            return {"status": "skipped", "message": "No papers to process"}

        papers_stored = fetch_results.get("papers_stored", 0)

        if papers_stored == 0:
            logger.info("No papers were stored, skipping OpenSearch indexing")
            return {"status": "skipped", "papers_indexed": 0, "message": "No papers available for indexing"}

        logger.info(f"Processing {papers_stored} papers for OpenSearch indexing")

        # Get services
        _arxiv_client, _pdf_parser, database, _metadata_fetcher, opensearch_client = get_cached_services()

        # Check OpenSearch health
        if not opensearch_client.health_check():
            logger.error("OpenSearch is not healthy, skipping indexing")
            return {"status": "failed", "papers_indexed": 0, "message": "OpenSearch cluster not healthy"}

        fetch_results = context["task_instance"].xcom_pull(task_ids="fetch_daily_papers", key="fetch_results")

        indexed_count = 0
        failed_count = 0

        with database.get_session() as session:
            paper_repo = PaperRepository(session)

            query = f"""
                SELECT * FROM papers 
                WHERE DATE(created_at) = CURRENT_DATE
                ORDER BY created_at DESC
                LIMIT {fetch_results.get("papers_stored", 0) if fetch_results else 100}
            """

            result = session.execute(text(query))
            papers = result.fetchall()

            logger.info(f"Found {len(papers)} papers from today's run to index")

            for paper_row in papers:
                try:
                    paper = paper_repo.get_by_id(paper_row.id)
                    if not paper:
                        continue
                    paper_doc = {
                        "arxiv_id": paper.arxiv_id,
                        "title": paper.title,
                        "authors": ", ".join(paper.authors) if isinstance(paper.authors, list) else str(paper.authors),
                        "abstract": paper.abstract,
                        "categories": paper.categories,
                        "pdf_url": paper.pdf_url,
                        "published_date": paper.published_date.isoformat()
                        if hasattr(paper.published_date, "isoformat")
                        else str(paper.published_date),
                        "raw_text": paper.raw_text
                        if hasattr(paper, "raw_text") and paper.raw_text
                        else "",  # Include PDF content
                        "created_at": paper.created_at.isoformat()
                        if hasattr(paper.created_at, "isoformat")
                        else str(paper.created_at),
                        "updated_at": paper.updated_at.isoformat()
                        if hasattr(paper.updated_at, "isoformat")
                        else str(paper.updated_at),
                    }

                    # Index the document
                    success = opensearch_client.index_paper(paper_doc)

                    if success:
                        indexed_count += 1
                        logger.info(f"Successfully indexed paper: {paper.arxiv_id}")
                    else:
                        failed_count += 1
                        logger.warning(f"Failed to index paper: {paper.arxiv_id}")

                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error indexing paper {paper_row.id}: {e}")

        # Get final index stats
        try:
            final_stats = opensearch_client.get_index_stats()
            total_docs = final_stats.get("document_count", 0) if final_stats else 0
        except Exception:
            total_docs = "unknown"

        indexing_results = {
            "status": "completed",
            "papers_indexed": indexed_count,
            "indexing_failures": failed_count,
            "total_documents_in_index": total_docs,
            "message": f"Indexed {indexed_count} papers, {failed_count} failures",
        }

        # Log detailed summary
        logger.info("=" * 60)
        logger.info("OpenSearch Indexing Summary:")
        logger.info(f"  Papers found in DB: {len(papers)}")
        logger.info(f"  Papers indexed: {indexed_count}")
        logger.info(f"  Indexing failures: {failed_count}")
        logger.info(f"  Total docs in index: {total_docs}")
        logger.info("=" * 60)

        return indexing_results

    except Exception as e:
        error_msg = f"OpenSearch indexing failed: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "papers_indexed": 0, "message": error_msg}

def generate_daily_report(**context):
    """
    Generate a daily processing report.

    This function:
    1. Collects results from all tasks
    2. Generates summary statistics
    3. Logs the daily report
    """
    logger.info("Generating daily processing report")

    try:
        fetch_results = context["task_instance"].xcom_pull(task_ids="fetch_daily_papers", key="fetch_results")

        failed_pdf_results = context["task_instance"].xcom_pull(task_ids="process_failed_pdfs")

        opensearch_results = context["task_instance"].xcom_pull(task_ids="create_opensearch_placeholders")

        report = {
            "date": context["ds"],
            "execution_time": datetime.now().isoformat(),
            "papers": {
                "fetched": fetch_results.get("papers_fetched", 0) if fetch_results else 0,
                "pdfs_downloaded": fetch_results.get("pdfs_downloaded", 0) if fetch_results else 0,
                "pdfs_parsed": fetch_results.get("pdfs_parsed", 0) if fetch_results else 0,
                "stored": fetch_results.get("papers_stored", 0) if fetch_results else 0,
            },
            "processing": {
                "processing_time_seconds": fetch_results.get("processing_time", 0) if fetch_results else 0,
                "errors": len(fetch_results.get("errors", [])) if fetch_results else 0,
                "failed_pdf_retries": failed_pdf_results.get("errors_logged", 0) if failed_pdf_results else 0,
            },
            "opensearch": {
                "placeholders_created": opensearch_results.get("papers_ready_for_indexing", 0) if opensearch_results else 0,
                "status": opensearch_results.get("status", "unknown") if opensearch_results else "unknown",
            },
        }

        logger.info("=== DAILY ARXIV PROCESSING REPORT ===")
        logger.info(f"Date: {report['date']}")
        logger.info(f"Papers fetched: {report['papers']['fetched']}")
        logger.info(f"PDFs downloaded: {report['papers']['pdfs_downloaded']}")
        logger.info(f"PDFs parsed: {report['papers']['pdfs_parsed']}")
        logger.info(f"Papers stored: {report['papers']['stored']}")
        logger.info(f"Processing time: {report['processing']['processing_time_seconds']:.1f}s")
        logger.info(f"Errors encountered: {report['processing']['errors']}")
        logger.info(f"OpenSearch placeholders: {report['opensearch']['placeholders_created']}")
        logger.info("=== END REPORT ===")

        return report

    except Exception as e:
        error_msg = f"Report generation failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
