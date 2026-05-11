from datetime import datetime, timedelta

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from arxiv_ingestion.fetching import fetch_daily_papers, fetch_metadata_only, process_pdfs
from arxiv_ingestion.filtering import check_scope_vector, filter_and_store_metadata
from arxiv_ingestion.indexing import index_papers_hybrid, verify_hybrid_index
from arxiv_ingestion.reporting import generate_daily_report

# Import task functions from modular structure
from arxiv_ingestion.setup import setup_environment

# Default DAG arguments
default_args = {
    "owner": "PaperLens",
    "depends_on_past": False,
    "start_date": datetime(2025, 8, 8),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=30),
    "catchup": False,
}

# Create the DAG
dag = DAG(
    "arxiv_paper_ingestion",
    default_args=default_args,
    description="Daily arXiv papers ingestion and processing pipeline (fetch → store to PostgreSQL → Hybrid Opensearch Indexing)",
    schedule="30 0 * * 1-5",  # Monday-Friday at 6 AM IST (excludes weekends)
    max_active_runs=1,
    catchup=False,
    tags=["arxiv", "papers", "ingestion", "hybrid_search", "embeddings"],
    params={
        # Backfill: set both dates (YYYYMMDD) to fetch a custom date range.
        # Leave blank for the normal daily run (fetches yesterday).
        "backfill_from_date": Param(
            default="",
            type="string",
            description="Start date for backfill (YYYYMMDD). Leave blank for normal daily run.",
        ),
        "backfill_to_date": Param(
            default="",
            type="string",
            description="End date for backfill (YYYYMMDD). Defaults to backfill_from_date if blank.",
        ),
        "max_results_override": Param(
            default=0,
            type="integer",
            description="Override max_results for this run (0 = use client default).",
        ),
        # Filtering control
        # False = skip all filtering, store every fetched paper (useful for backfill / testing)
        "enable_filtering": Param(
            default=True,
            type="boolean",
            description="Set to false to bypass all filtering and ingest every fetched paper.",
        ),
    },
)

# Task definitions
setup_task = PythonOperator(
    task_id="setup_environment",
    python_callable=setup_environment,
    dag=dag,
)

fetch_task = PythonOperator(
    task_id="fetch_paper_metadata",
    python_callable=fetch_metadata_only,
    dag=dag,
)

scope_vector_task = PythonOperator(
    task_id="scope_vector_check",
    python_callable=check_scope_vector,
    dag=dag,
)

filter_task = PythonOperator(
    task_id="filter_papers",
    python_callable=filter_and_store_metadata,
    dag=dag,
)

process_pdf_task = PythonOperator(
    task_id="process_filtered_pdf",
    python_callable=process_pdfs,
    dag=dag,
)


# Hybrid search indexing task (replaces old OpenSearch task)
index_hybrid_task = PythonOperator(
    task_id="index_papers_hybrid",
    python_callable=index_papers_hybrid,
    dag=dag,
)

report_task = PythonOperator(
    task_id="generate_daily_report",
    python_callable=generate_daily_report,
    dag=dag,
)

cleanup_task = BashOperator(
    task_id="cleanup_temp_files",
    bash_command="""
    echo "Cleaning up temporary files..."
    # Remove PDFs older than 30 days to manage disk space
    find /tmp -name "*.pdf" -type f -mtime +30 -delete 2>/dev/null || true
    echo "Cleanup completed"
    """,
    dag=dag,
)

# Task dependencies
# Main pipeline: setup -> fetch -> (retry + opensearch) -> report -> cleanup
setup_task >> fetch_task >> scope_vector_task >> filter_task >> process_pdf_task >> index_hybrid_task >> report_task >> cleanup_task
