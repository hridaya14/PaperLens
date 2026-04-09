"""
build_eval_dataset.py
─────────────────────
Phase 1 — Build the ground-truth evaluation dataset for PaperLens.

Uses your live /hybrid-search API directly — no service imports needed.

Strategy
--------
"Title-as-query":  each paper's title is sent to POST /hybrid-search/
with use_hybrid=false (BM25 only). The chunks returned become the
ground-truth relevant documents for that query.

BM25 is intentionally used for ground-truth construction so the
relevance labels are model-agnostic — the vector model being evaluated
does not influence which documents are marked as relevant.

Output
------
  eval/data/qrels.json            ranx-format relevance judgements
  eval/data/queries.json          query_id → query text
  eval/data/dataset_summary.json  stats about the generated set
  eval/data/manual_review.csv     30-paper subset for human annotation

Usage
-----
  # From your project root (API must be running):
  python eval/build_eval_dataset.py

  # Point at a non-default API URL:
  python eval/build_eval_dataset.py --api-url http://localhost:9000

  # Limit paper count for a quick test:
  python eval/build_eval_dataset.py --limit 20

  # Skip live API — use hardcoded sample data to test the pipeline:
  python eval/build_eval_dataset.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── paths ─────────────────────────────────────────────────────────────────────
EVAL_DIR = Path(__file__).parent
DATA_DIR = EVAL_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

QRELS_PATH = DATA_DIR / "qrels.json"
QUERIES_PATH = DATA_DIR / "queries.json"
SUMMARY_PATH = DATA_DIR / "dataset_summary.json"
MANUAL_REVIEW_PATH = DATA_DIR / "manual_review.csv"

# ── defaults ──────────────────────────────────────────────────────────────────
DEFAULT_API_URL = "http://localhost:8000/api/v1"
DEFAULT_PAPER_LIMIT = 100
MANUAL_REVIEW_COUNT = 30

# Retrieval config for ground-truth construction
GROUND_TRUTH_TOP_K = 20  # chunks fetched per title query
GROUND_TRUTH_MIN_SCORE = 0.0  # include all returned results

# Relevance scores written into qrels
RELEVANCE_AUTO = 1  # title-as-query BM25 match
RELEVANCE_MANUAL_HIGH = 2  # reviewer bumps this in manual_review.csv


# ─────────────────────────────────────────────────────────────────────────────
# ID helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_query_id(paper_id: str) -> str:
    """Stable short ID derived from paper DB id."""
    return f"q_{hashlib.md5(str(paper_id).encode()).hexdigest()[:10]}"


def make_doc_id(chunk_id: str | None, arxiv_id: str | None, fallback: str) -> str:
    """
    Build a doc ID from whatever the API returns.
    Prefer chunk_id (most specific), then arxiv_id, then fallback.
    """
    if chunk_id:
        return str(chunk_id)
    if arxiv_id:
        return str(arxiv_id)
    return str(fallback)


# ─────────────────────────────────────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────────────────────────────────────


async def check_api_health(client: httpx.AsyncClient, api_url: str) -> bool:
    """Ping /ping (or /health) before starting — fail fast if API is down."""
    for path in ["/ping", "/health", "/"]:
        try:
            r = await client.get(f"{api_url}{path}", timeout=5.0)
            if r.status_code < 500:
                log.info("API is reachable at %s%s", api_url, path)
                return True
        except Exception:
            continue
    return False


async def search_via_api(
    client: httpx.AsyncClient,
    api_url: str,
    query: str,
    use_hybrid: bool = False,
    size: int = GROUND_TRUTH_TOP_K,
    min_score: float = GROUND_TRUTH_MIN_SCORE,
) -> dict[str, Any]:
    """
    Call POST /hybrid-search/ and return the parsed SearchResponse dict.

    Set use_hybrid=False for ground-truth construction (BM25 only).
    Set use_hybrid=True for the hybrid evaluation run.
    """
    payload = {
        "query": query,
        "use_hybrid": use_hybrid,
        "size": size,
        "from_": 0,
        "min_score": min_score,
        # leave categories / latest_papers at defaults
    }

    response = await client.post(
        f"{api_url}/hybrid-search/",
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


async def fetch_papers_from_api(
    client: httpx.AsyncClient,
    api_url: str,
    limit: int,
) -> list[dict]:
    """
    Fetch the paper list from GET /papers/ (adjust path if yours differs).
    Returns a list of { id, title, abstract, arxiv_id } dicts.
    """
    try:
        # Try paginated endpoint first
        response = await client.get(
            f"{api_url}/papers/",
            params={"limit": limit, "offset": 0},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        # Handle both list and paginated envelope responses
        if isinstance(data, list):
            papers = data
        elif isinstance(data, dict):
            papers = data.get("items", data.get("papers", data.get("results", [])))
        else:
            papers = []

        log.info("Fetched %d papers from API", len(papers))
        return papers[:limit]

    except Exception as exc:
        log.error("Could not fetch papers from API: %s", exc)
        log.info(
            "Tip: adjust the /papers/ path in fetch_papers_from_api() to match your actual papers endpoint, or use --dry-run"
        )
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Dry-run / sample data
# ─────────────────────────────────────────────────────────────────────────────


def _sample_papers(limit: int) -> list[dict]:
    log.warning("DRY RUN — using hardcoded sample papers. Results will not reflect your real index.")
    samples = [
        {
            "id": f"sample_{i}",
            "title": title,
            "abstract": abstract,
            "arxiv_id": f"2401.{i:05d}",
        }
        for i, (title, abstract) in enumerate(
            [
                ("Attention Is All You Need", "We propose the Transformer architecture based solely on attention mechanisms."),
                (
                    "BERT: Pre-training of Deep Bidirectional Transformers",
                    "BERT pre-trains deep bidirectional representations from unlabeled text.",
                ),
                (
                    "Dense Passage Retrieval for Open-Domain Question Answering",
                    "Retrieval implemented using dense representations learned from questions.",
                ),
                (
                    "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                    "A general-purpose recipe for RAG models combining retrieval and generation.",
                ),
                (
                    "Improving Language Understanding by Generative Pre-Training",
                    "Large gains on NLP tasks via generative pre-training on unlabeled text.",
                ),
            ],
            1,
        )
    ]
    return samples[:limit]


def _mock_search_response(query: str, paper_id: str) -> dict:
    """Fake SearchResponse for dry-run mode."""
    return {
        "query": query,
        "total": 1,
        "hits": [
            {
                "arxiv_id": paper_id,
                "title": query,
                "chunk_id": f"chunk_{paper_id}_0",
                "score": 9.5,
            }
        ],
        "search_mode": "bm25",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Core builder
# ─────────────────────────────────────────────────────────────────────────────


async def build_dataset(
    api_url: str,
    limit: int,
    dry_run: bool,
) -> tuple[dict, dict, list[dict]]:
    """
    Fetch papers, run title-as-query BM25 searches, build qrels + queries.
    """
    log.info("═══ Building evaluation dataset ═══")
    log.info("API: %s | Papers: %d | Dry run: %s", api_url, limit, dry_run)

    async with httpx.AsyncClient() as client:
        # ── health check ──────────────────────────────────────────────────────
        if not dry_run:
            ok = await check_api_health(client, api_url)
            if not ok:
                log.error(
                    "Cannot reach API at %s\n"
                    "  • Make sure the server is running (uvicorn src.main:app)\n"
                    "  • Or pass --dry-run to use sample data",
                    api_url,
                )
                sys.exit(1)

        # ── fetch paper list ──────────────────────────────────────────────────
        if dry_run:
            papers = _sample_papers(limit)
        else:
            papers = await fetch_papers_from_api(client, api_url, limit)
            if not papers:
                log.error("No papers returned from API — cannot build dataset")
                sys.exit(1)

        # ── title-as-query BM25 lookups ───────────────────────────────────────
        qrels: dict[str, dict[str, int]] = {}
        queries: dict[str, str] = {}
        manual_rows: list[dict] = []

        total = len(papers)
        for idx, paper in enumerate(papers, 1):
            paper_id = str(paper.get("id") or paper.get("arxiv_id", f"paper_{idx}"))
            title = (paper.get("title") or "").strip()
            abstract = (paper.get("abstract") or "")[:300]
            arxiv_id = paper.get("arxiv_id", "")

            if not title:
                log.debug("Skipping paper %s — no title", paper_id)
                continue

            query_id = make_query_id(paper_id)
            queries[query_id] = title

            # ── BM25 search via API ───────────────────────────────────────────
            try:
                if dry_run:
                    search_resp = _mock_search_response(title, paper_id)
                else:
                    search_resp = await search_via_api(
                        client,
                        api_url,
                        title,
                        use_hybrid=False,  # BM25 only for ground truth
                        size=GROUND_TRUTH_TOP_K,
                    )
            except httpx.HTTPStatusError as exc:
                log.warning("API error for query '%s': %s — skipping", title[:50], exc)
                continue
            except Exception as exc:
                log.warning("Search failed for query '%s': %s — skipping", title[:50], exc)
                continue

            # ── build relevance judgements from returned hits ─────────────────
            hits = search_resp.get("hits", [])
            relevant_docs: dict[str, int] = {}

            for hit in hits:
                doc_id = make_doc_id(
                    hit.get("chunk_id"),
                    hit.get("arxiv_id"),
                    fallback=f"doc_{idx}_{len(relevant_docs)}",
                )
                relevant_docs[doc_id] = RELEVANCE_AUTO

            if not relevant_docs:
                # Fallback: mark the paper itself as relevant
                relevant_docs[paper_id] = RELEVANCE_AUTO

            qrels[query_id] = relevant_docs

            # ── collect manual review rows ────────────────────────────────────
            if idx <= MANUAL_REVIEW_COUNT:
                manual_rows.append(
                    {
                        "query_id": query_id,
                        "paper_id": paper_id,
                        "arxiv_id": arxiv_id,
                        "title": title,
                        "abstract_preview": abstract + ("..." if len(abstract) == 300 else ""),
                        "auto_chunks_found": len(relevant_docs),
                        "relevance_score": RELEVANCE_AUTO,  # reviewer: bump to 2 for high-relevance
                        "notes": "",
                    }
                )

            if idx % 10 == 0 or idx == total:
                log.info("  Progress: %d / %d  |  chunks found this query: %d", idx, total, len(relevant_docs))

    return qrels, queries, manual_rows


# ─────────────────────────────────────────────────────────────────────────────
# Save outputs
# ─────────────────────────────────────────────────────────────────────────────


def save_outputs(
    qrels: dict,
    queries: dict,
    manual_rows: list[dict],
    api_url: str,
    dry_run: bool,
) -> None:

    with open(QRELS_PATH, "w") as f:
        json.dump(qrels, f, indent=2)
    log.info("Saved qrels     → %s  (%d queries)", QRELS_PATH, len(qrels))

    with open(QUERIES_PATH, "w") as f:
        json.dump(queries, f, indent=2)
    log.info("Saved queries   → %s", QUERIES_PATH)

    if manual_rows:
        with open(MANUAL_REVIEW_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(manual_rows[0].keys()))
            writer.writeheader()
            writer.writerows(manual_rows)
        log.info("Saved manual review → %s  (%d rows)", MANUAL_REVIEW_PATH, len(manual_rows))

    total_relevant = sum(len(v) for v in qrels.values())
    summary = {
        "generated_at": datetime.now().isoformat(),
        "api_url": api_url,
        "dry_run": dry_run,
        "total_queries": len(qrels),
        "total_relevant_docs": total_relevant,
        "avg_relevant_per_query": round(total_relevant / max(len(qrels), 1), 2),
        "manual_review_count": len(manual_rows),
        "ground_truth_method": "title-as-query BM25 via /hybrid-search/ (use_hybrid=false)",
        "relevance_scale": "1=auto BM25 match  2=manual high-relevance",
    }
    with open(SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2)

    _print_summary(summary)


def _print_summary(s: dict) -> None:
    print("\n" + "═" * 56)
    print("  Dataset Summary")
    print("═" * 56)
    print(f"  Total queries          : {s['total_queries']}")
    print(f"  Total relevant docs    : {s['total_relevant_docs']}")
    print(f"  Avg relevant / query   : {s['avg_relevant_per_query']}")
    print(f"  Manual review rows     : {s['manual_review_count']}")
    print("─" * 56)
    print("  Next steps:")
    print("  1. Open eval/data/manual_review.csv")
    print("     → Set relevance_score=2 for your best papers")
    print("     → Add notes for interesting edge cases")
    print("  2. python eval/run_retrieval_eval.py")
    print("═" * 56 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build PaperLens retrieval evaluation dataset via the live API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--api-url", default=DEFAULT_API_URL, help=f"Base URL of your running FastAPI server (default: {DEFAULT_API_URL})"
    )
    p.add_argument(
        "--limit", type=int, default=DEFAULT_PAPER_LIMIT, help=f"Number of papers to include (default: {DEFAULT_PAPER_LIMIT})"
    )
    p.add_argument("--dry-run", action="store_true", help="Use sample data — no live API needed. For pipeline testing only.")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    t0 = time.perf_counter()

    qrels, queries, manual_rows = asyncio.run(
        build_dataset(
            api_url=args.api_url,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    )
    save_outputs(qrels, queries, manual_rows, args.api_url, args.dry_run)

    log.info("Done in %.1fs", time.perf_counter() - t0)
