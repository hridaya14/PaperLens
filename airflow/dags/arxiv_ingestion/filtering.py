"""
Filtering tasks for the arXiv ingestion DAG.

Two tasks:

  check_scope_vector        — ensures the active scope profile's embedding
                              centroid is up to date before filtering begins

  filter_and_store_metadata — runs the full filter stack (lexical → embedding
                              → LLM reranker), stores metadata for ingested
                              papers to PostgreSQL, and writes filter decisions
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.schemas.arxiv.paper import ArxivPaper, PaperCreate

from .common import get_cached_services, get_filtering_services

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task 1 — Scope vector check
# ---------------------------------------------------------------------------


async def _ensure_scope_vector() -> Optional[dict]:
    """Check whether the active profile's scope vector needs recomputing.

    Returns a summary dict for XCom, or None if no active profile exists.
    """
    from src.repositories.paper import PaperRepository
    from src.repositories.scope_profile import ScopeProfileRepository
    from src.services.filtering.embedding import compute_scope_vector

    _, _, database, _, _ = get_cached_services()
    embeddings_client, _ = get_filtering_services()

    with database.get_session() as session:
        scope_repo = ScopeProfileRepository(session)
        profile = scope_repo.get_active()

        if not profile:
            logger.info("No active scope profile found — filtering disabled for this run")
            return None

        if not scope_repo.needs_vector_recompute(profile):
            logger.info(f"Scope vector for '{profile.name}' is current (computed_at={profile.scope_vector_computed_at})")
            return {
                "profile_id": str(profile.id),
                "profile_name": profile.name,
                "version_hash": profile.version_hash,
                "vector_recomputed": False,
                "vector_dims": len(profile.scope_vector) if profile.scope_vector else 0,
            }

        logger.info(f"Scope vector for '{profile.name}' is stale or missing — recomputing")

        # Fetch seed paper abstracts from DB
        seed_abstracts = []
        paper_repo = PaperRepository(session)
        for arxiv_id in profile.seed_paper_ids or []:
            paper = paper_repo.get_by_arxiv_id(arxiv_id)
            if paper and paper.abstract:
                seed_abstracts.append(paper.abstract)
            else:
                logger.warning(f"Seed paper '{arxiv_id}' not in DB — skipping")

        vector = await compute_scope_vector(
            profile=profile,
            embeddings_client=embeddings_client,
            seed_paper_abstracts=seed_abstracts or None,
        )

        scope_repo.update_scope_vector(profile.id, vector)
        logger.info(
            f"Scope vector recomputed for '{profile.name}': {len(vector)} dims, {len(seed_abstracts)} seed abstracts used"
        )

        return {
            "profile_id": str(profile.id),
            "profile_name": profile.name,
            "version_hash": profile.version_hash,
            "vector_recomputed": True,
            "vector_dims": len(vector),
            "seed_papers_used": len(seed_abstracts),
        }


def check_scope_vector(**context) -> dict:
    """Airflow task: ensure the active scope profile's vector is ready.

    Must run before filter_and_store_metadata. If no active profile
    exists, the filter task will skip filtering and ingest all papers.

    XCom pushed:
      key="scope_info" → profile metadata dict or None
    """
    logger.info("Checking scope vector readiness")

    result = asyncio.run(_ensure_scope_vector())

    ti = context.get("ti")
    if ti:
        ti.xcom_push(key="scope_info", value=result)

    if result:
        recomputed = "recomputed" if result["vector_recomputed"] else "already current"
        logger.info(f"Scope vector {recomputed} for profile '{result['profile_name']}' (version={result['version_hash'][:8]}...)")
    else:
        logger.info("No active scope profile — pipeline will ingest all papers")

    return result or {}


# ---------------------------------------------------------------------------
# Task 2 — Filter + store metadata
# ---------------------------------------------------------------------------


async def _run_filter_and_store(
    papers_data: List[dict],
    target_date: str,
    enable_filtering: bool = True,
) -> dict:
    """Run the filter stack and store metadata for ingested papers.

    Flow:
      1. If enable_filtering=False or no active profile → store all papers, skip filter stack
      2. Otherwise: run lexical → embedding → LLM reranker
      3. Store metadata for ingested papers to PostgreSQL
      4. Write filter decisions to DB
      5. Return ingested paper list for PDF processing

    :param papers_data: Serialised ArxivPaper dicts from XCom
    :param target_date: YYYYMMDD string (for logging)
    :param enable_filtering: When False, bypass all filtering and ingest every paper
    :returns: Results dict with ingested papers and filter stats
    """
    from dateutil import parser as date_parser
    from src.config import get_settings
    from src.services.metadata_fetcher import clean_json, clean_value
    from src.repositories.paper import PaperRepository
    from src.repositories.scope_profile import ScopeProfileRepository
    from src.schemas.scope.profile import FilterDecisionCreate
    from src.services.filtering.embedding import EmbeddingFilter
    from src.services.filtering.lexical import LexicalFilter
    from src.services.filtering.reranker import LLMReranker
    from src.services.filtering.scorer import CompositeScorer, PaperSignals

    _, _, database, _, _ = get_cached_services()
    embeddings_client, llm_client = get_filtering_services()
    settings = get_settings()

    papers = [ArxivPaper(**p) for p in papers_data]

    results = {
        "total_candidates": len(papers),
        "ingested_count": 0,
        "rejected_count": 0,
        "filtering_enabled": False,
        "filter_stats": {},
        "ingested_papers": [],
        "errors": [],
    }

    with database.get_session() as session:
        scope_repo = ScopeProfileRepository(session)
        paper_repo = PaperRepository(session)
        profile = scope_repo.get_active()

        # ----------------------------------------------------------------
        # Decide whether filtering runs
        # ----------------------------------------------------------------

        ingested_papers = papers  # Default: ingest everything

        # Accumulate layer outputs for decision writing
        lexical_result = None
        embedding_result = None
        reranker_result = None

        if not enable_filtering:
            logger.info(
                f"Filtering disabled via DAG param — ingesting all {len(papers)} papers"
            )
        elif not profile:
            logger.info(
                "No active scope profile found — ingesting all "
                f"{len(papers)} papers without filtering"
            )
        elif profile and settings.filtering.enabled:
            results["filtering_enabled"] = True
            logger.info(
                f"Filtering {len(papers)} papers against profile '{profile.name}' (version={profile.version_hash[:8]}...)"
            )

            # Layer 1 — Lexical
            lexical = LexicalFilter(profile)
            lexical_result = lexical.filter_batch(papers)

            # Layer 2 — Embedding
            embedding_filter = EmbeddingFilter(profile, embeddings_client)
            embedding_result = await embedding_filter.filter_batch(lexical_result.passed)

            # Layer 3 — LLM reranker (ambiguous zone only)
            if settings.filtering.llm_reranking_enabled and embedding_result.ambiguous:
                reranker = LLMReranker(
                    profile=profile,
                    llm_client=llm_client,
                    max_papers=settings.filtering.llm_rerank_max_papers,
                )
                reranker_result = reranker.rerank_batch(embedding_result.ambiguous)
            else:
                # No ambiguous papers or reranker disabled — empty result
                from src.services.filtering.reranker import RerankerBatchResult

                reranker_result = RerankerBatchResult(results=[])

            # Determine final ingested set
            llm_accepted = [r.paper for r in reranker_result.results if r.relevant]
            ingested_papers = embedding_result.fast_track_ingest + llm_accepted

            results["filter_stats"] = {
                "lexical_passed": lexical_result.passed_count,
                "lexical_rejected": lexical_result.rejected_count,
                "fast_track_ingest": len(embedding_result.fast_track_ingest),
                "fast_track_reject": len(embedding_result.fast_track_reject),
                "sent_to_llm": len(embedding_result.ambiguous),
                "llm_accepted": len(llm_accepted),
                "llm_rejected": len(embedding_result.ambiguous) - len(llm_accepted),
                "total_ingested": len(ingested_papers),
            }

            logger.info(
                f"Filter complete: {len(ingested_papers)}/{len(papers)} papers ingested "
                f"({results['filter_stats']['lexical_rejected']} lexical rejects, "
                f"{results['filter_stats']['fast_track_reject']} embedding rejects, "
                f"{results['filter_stats']['llm_rejected']} LLM rejects)"
            )
        else:
            logger.info("Filtering disabled or no active profile — ingesting all papers")

        results["ingested_count"] = len(ingested_papers)
        results["rejected_count"] = len(papers) - len(ingested_papers)

        # ----------------------------------------------------------------
        # Store metadata for ingested papers (no PDF content yet)
        # ----------------------------------------------------------------

        paper_id_map: Dict[str, Any] = {}  # arxiv_id → UUID
        stored_count = 0

        for paper in ingested_papers:
            try:
                published_date = (
                    date_parser.parse(paper.published_date) if isinstance(paper.published_date, str) else paper.published_date
                )
                paper_create = PaperCreate(
                    arxiv_id=clean_value(paper.arxiv_id),
                    title=clean_value(paper.title),
                    authors=clean_value(paper.authors),
                    abstract=clean_value(paper.abstract),
                    categories=clean_value(paper.categories),
                    published_date=published_date,
                    pdf_url=clean_value(paper.pdf_url),
                    pdf_processed=False,
                    parser_metadata=clean_json({"note": "Metadata stored; PDF processing pending"}),
                )
                stored = paper_repo.upsert(paper_create)
                if stored:
                    paper_id_map[paper.arxiv_id] = stored.id
                    stored_count += 1
            except Exception as e:
                logger.error(f"Failed to store metadata for {paper.arxiv_id}: {e}")
                results["errors"].append(f"Metadata store failed: {paper.arxiv_id}: {e}")
                session.rollback()
                continue

        try:
            session.commit()
            logger.info(f"Stored metadata for {stored_count} papers")
        except Exception as e:
            logger.error(f"Failed to commit metadata: {e}")
            session.rollback()

        # ----------------------------------------------------------------
        # Write filter decisions (requires UUIDs from store step)
        # ----------------------------------------------------------------

        if profile and lexical_result and embedding_result and reranker_result:
            try:
                scorer = CompositeScorer(
                    profile=profile,
                    ingest_threshold=(
                        (profile.thresholds or {}).get("composite_ingest")
                        or settings.filtering.composite_ingest_threshold
                    ),
                )
                all_signals = scorer.assemble_signals(
                    lexical_result,
                    embedding_result,
                    reranker_result,
                    paper_id_map,
                )
                decisions = [
                    scorer.build_filter_decision(s, profile.id)
                    for s in all_signals
                    if s.paper_id is not None  # Skip papers that failed to store
                ]
                written = scope_repo.write_filter_decisions_bulk(decisions)
                logger.info(f"Wrote {written} filter decisions to DB")
                results["filter_stats"]["decisions_written"] = written
            except Exception as e:
                logger.error(f"Failed to write filter decisions: {e}")
                results["errors"].append(f"Filter decision write failed: {e}")

    # Serialise ingested papers for XCom (process_pdfs task)
    results["ingested_papers"] = [p.model_dump() for p in ingested_papers]
    return results


def filter_and_store_metadata(**context) -> dict:
    """Airflow task: filter papers and store metadata for ingested ones.

    Respects the ``enable_filtering`` DAG param. When False, or when no active
    scope profile exists, all fetched papers are stored without filtering.

    XCom consumed:
      task_id="fetch_metadata_only", key="papers"
      task_id="fetch_metadata_only", key="fetch_date"

    XCom pushed:
      key="ingested_papers"   → list of ArxivPaper dicts (for process_pdfs)
      key="filter_results"    → stats dict (for reporting)
    """
    logger.info("Starting filter and metadata store task")

    ti = context.get("ti")
    params = context.get("params") or {}
    enable_filtering = bool(params.get("enable_filtering", True))

    papers_data = []
    target_date = "unknown"

    if ti:
        papers_data = ti.xcom_pull(task_ids="fetch_paper_metadata", key="papers") or []
        target_date = ti.xcom_pull(task_ids="fetch_paper_metadata", key="fetch_date") or "unknown"

    if not papers_data:
        logger.warning("No papers received from fetch task — nothing to filter")
        empty = {
            "total_candidates": 0,
            "ingested_count": 0,
            "ingested_papers": [],
            "filter_stats": {},
            "errors": [],
        }
        if ti:
            ti.xcom_push(key="ingested_papers", value=[])
            ti.xcom_push(key="filter_results", value=empty)
        return empty

    logger.info(
        f"Received {len(papers_data)} papers for processing "
        f"(date={target_date}, enable_filtering={enable_filtering})"
    )

    results = asyncio.run(
        _run_filter_and_store(papers_data, target_date, enable_filtering=enable_filtering)
    )

    logger.info(f"Filter+store complete: {results['ingested_count']}/{results['total_candidates']} ingested")

    if ti:
        ti.xcom_push(key="ingested_papers", value=results["ingested_papers"])
        ti.xcom_push(
            key="filter_results",
            value={
                "total_candidates": results["total_candidates"],
                "ingested_count": results["ingested_count"],
                "rejected_count": results["rejected_count"],
                "filtering_enabled": results["filtering_enabled"],
                "filter_stats": results["filter_stats"],
                "error_count": len(results["errors"]),
            },
        )

    return results
