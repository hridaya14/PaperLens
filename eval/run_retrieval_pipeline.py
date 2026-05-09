"""
run_retrieval_eval.py
─────────────────────
Phase 1 — Compare BM25 vs hybrid retrieval by calling POST /hybrid-search/.

The same endpoint, same middleware, same embedding path your users hit.
Toggling use_hybrid=false/true is all that distinguishes the two strategies.

Usage
-----
  # Full evaluation (API must be running):
  python eval/run_retrieval_eval.py

  # BM25 only:
  python eval/run_retrieval_eval.py --strategies bm25

  # Custom K values:
  python eval/run_retrieval_eval.py --k 3 5 10 20

  # Different API URL:
  python eval/run_retrieval_eval.py --api-url http://localhost:9000

  # Dry run (no live API):
  python eval/run_retrieval_eval.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from ranx import Qrels, Run, compare, evaluate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── paths ─────────────────────────────────────────────────────────────────────
EVAL_DIR = Path(__file__).parent
DATA_DIR = EVAL_DIR / "data"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

QRELS_PATH = DATA_DIR / "qrels.json"
QUERIES_PATH = DATA_DIR / "queries.json"

# ── evaluation config ─────────────────────────────────────────────────────────
DEFAULT_API_URL = "http://localhost:8000/api/v1"
DEFAULT_STRATEGIES = ["bm25", "hybrid"]
DEFAULT_K_VALUES = [1, 3, 5, 10]
DEFAULT_TOP_K = 20  # size= sent to the API per query
PRIMARY_METRIC = "ndcg@10"

METRICS_TEMPLATES = [
    "precision@{k}",
    "recall@{k}",
    "ndcg@{k}",
    "mrr@{k}",
    "hit_rate@{k}",
]

# Maps strategy name → use_hybrid value to send in the request body
STRATEGY_FLAGS: dict[str, bool] = {
    "bm25": False,
    "hybrid": True,
}


# ─────────────────────────────────────────────────────────────────────────────
# API call
# ─────────────────────────────────────────────────────────────────────────────


async def search(
    client: httpx.AsyncClient,
    api_url: str,
    query: str,
    use_hybrid: bool,
    top_k: int,
) -> tuple[list[tuple[str, float]], float]:
    """
    Call POST /hybrid-search/ for one query.

    Returns
    -------
    results   : [(doc_id, score), ...]  ordered by score descending
    latency_ms: wall-clock time for the HTTP round trip in milliseconds
    """
    payload = {
        "query": query,
        "use_hybrid": use_hybrid,
        "size": top_k,
        "from_": 0,
    }

    t0 = time.perf_counter()
    response = await client.post(
        f"{api_url}/hybrid-search/",
        json=payload,
        timeout=30.0,
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    response.raise_for_status()
    data = response.json()

    results = []
    for hit in data.get("hits", []):
        # Use chunk_id if present (most specific), fall back to arxiv_id
        doc_id = hit.get("chunk_id") or hit.get("arxiv_id") or ""
        score = float(hit.get("score", 0.0))
        if doc_id and score > 0:
            results.append((str(doc_id), score))

    return results, latency_ms


# ─────────────────────────────────────────────────────────────────────────────
# Dry-run mocks
# ─────────────────────────────────────────────────────────────────────────────


def _mock_results(
    query_id: str,
    qrels_raw: dict,
    use_hybrid: bool,
) -> tuple[list[tuple[str, float]], float]:
    """
    Simulate realistic retrieval results for pipeline testing.
    BM25 mock: ~65% recall.  Hybrid mock: ~82% recall.
    """
    import random

    seed = hash(query_id + ("h" if use_hybrid else "b")) & 0xFFFFFFFF
    rng = random.Random(seed)

    relevant = list(qrels_raw.get(query_id, {}).keys())
    recall = 0.82 if use_hybrid else 0.65
    n_found = max(1, int(len(relevant) * recall))
    found = rng.sample(relevant, min(n_found, len(relevant)))

    results = [(doc_id, 10.0 - i * 0.5) for i, doc_id in enumerate(found)]
    noise_n = max(0, 10 - len(results))
    results += [(f"noise_{query_id}_{j}", 3.0 - j * 0.2) for j in range(noise_n)]

    latency_ms = rng.uniform(20, 50) if not use_hybrid else rng.uniform(38, 85)
    return results, latency_ms


# ─────────────────────────────────────────────────────────────────────────────
# Strategy runner
# ─────────────────────────────────────────────────────────────────────────────


async def run_strategy(
    strategy: str,
    queries: dict[str, str],
    qrels_raw: dict,
    api_url: str,
    top_k: int,
    dry_run: bool,
) -> tuple[dict[str, dict[str, float]], list[float]]:
    """
    Run all queries through one strategy.

    Returns
    -------
    run_dict  : ranx Run format  { query_id: { doc_id: score } }
    latencies : per-query HTTP round-trip in ms
    """
    use_hybrid = STRATEGY_FLAGS[strategy]
    run_dict: dict[str, dict[str, float]] = {}
    latencies: list[float] = []

    log.info("Strategy: %-8s  use_hybrid=%-5s  queries=%d  top_k=%d", strategy, use_hybrid, len(queries), top_k)

    async with httpx.AsyncClient() as client:
        for i, (qid, qtext) in enumerate(queries.items(), 1):
            try:
                if dry_run:
                    results, lat = _mock_results(qid, qrels_raw, use_hybrid)
                else:
                    results, lat = await search(client, api_url, qtext, use_hybrid, top_k)
            except httpx.HTTPStatusError as exc:
                log.warning("  [%d] HTTP %s for query '%s' — skipping", i, exc.response.status_code, qtext[:50])
                results, lat = [], 0.0
            except Exception as exc:
                log.warning("  [%d] Error for query '%s': %s — skipping", i, qtext[:50], exc)
                results, lat = [], 0.0

            latencies.append(lat)
            run_dict[qid] = {doc_id: score for doc_id, score in results}

            if i % 20 == 0 or i == len(queries):
                window = latencies[max(0, i - 20) :]
                avg_lat = sum(window) / len(window)
                log.info("  [%d/%d]  avg latency (last batch): %.1f ms", i, len(queries), avg_lat)

    return run_dict, latencies


# ─────────────────────────────────────────────────────────────────────────────
# Latency stats
# ─────────────────────────────────────────────────────────────────────────────


def latency_stats(latencies: list[float]) -> dict[str, float]:
    if not latencies:
        return {}
    s = sorted(latencies)
    n = len(s)

    def pct(p: float) -> float:
        return s[min(int(p / 100 * n), n - 1)]

    return {
        "p50": round(pct(50), 1),
        "p95": round(pct(95), 1),
        "p99": round(pct(99), 1),
        "mean": round(sum(latencies) / n, 1),
        "min": round(s[0], 1),
        "max": round(s[-1], 1),
        "count": n,
        "all_ms": latencies,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────────────────────


def print_metrics_table(
    report: dict[str, dict],
    strategies: list[str],
    k_values: list[int],
) -> None:
    COL = 14
    print("\n" + "═" * (22 + COL * len(strategies)))
    print("  Table 1 — Retrieval Strategy Comparison (PaperLens)")
    print("═" * (22 + COL * len(strategies)))
    print(f"{'Metric':<22}" + "".join(f"{s:>{COL}}" for s in strategies))
    print("─" * (22 + COL * len(strategies)))

    for k in k_values:
        for m in ["precision", "recall", "ndcg", "mrr", "hit_rate"]:
            key = f"{m}@{k}"
            row = f"{key:<22}"
            for s in strategies:
                v = report.get(s, {}).get(key)
                row += f"{v:>{COL}.4f}" if v is not None else f"{'N/A':>{COL}}"
            print(row)

    print("═" * (22 + COL * len(strategies)))


def print_latency_table(
    lat_stats: dict[str, dict],
    strategies: list[str],
) -> None:
    COL = 10
    headers = ["P50", "P95", "P99", "Mean", "Min", "Max"]
    keys = ["p50", "p95", "p99", "mean", "min", "max"]

    print("\n" + "═" * (14 + COL * len(headers)))
    print("  Latency (ms) — full HTTP round-trip including middleware")
    print("═" * (14 + COL * len(headers)))
    print(f"{'Strategy':<14}" + "".join(f"{h:>{COL}}" for h in headers))
    print("─" * (14 + COL * len(headers)))
    for s in strategies:
        row = f"{s:<14}"
        for k in keys:
            v = lat_stats.get(s, {}).get(k)
            row += f"{v:>{COL}.1f}" if v is not None else f"{'N/A':>{COL}}"
        print(row)
    print("═" * (14 + COL * len(headers)))


def print_delta_summary(
    report: dict,
    lat_stats: dict,
    strategies: list[str],
) -> None:
    if "bm25" not in report or "hybrid" not in report:
        return

    bm25_v = report["bm25"].get(PRIMARY_METRIC, 0)
    hybrid_v = report["hybrid"].get(PRIMARY_METRIC, 0)
    delta = hybrid_v - bm25_v
    pct = (delta / bm25_v * 100) if bm25_v > 0 else 0.0

    bm25_p95 = lat_stats.get("bm25", {}).get("p95", 0)
    hybrid_p95 = lat_stats.get("hybrid", {}).get("p95", 0)
    lat_cost = hybrid_p95 - bm25_p95

    print(f"\n  ► {PRIMARY_METRIC:12s}  bm25={bm25_v:.4f}  hybrid={hybrid_v:.4f}  Δ={delta:+.4f} ({pct:+.1f}%)")
    print(f"  ► P95 latency    bm25={bm25_p95:.1f}ms  hybrid={hybrid_p95:.1f}ms  cost={lat_cost:+.1f}ms\n")


def save_results(
    report: dict,
    lat_stats: dict,
    strategies: list[str],
    k_values: list[int],
    api_url: str,
    dry_run: bool,
) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "generated_at": datetime.now().isoformat(),
        "api_url": api_url,
        "dry_run": dry_run,
        "strategies": strategies,
        "k_values": k_values,
        "metrics": report,
        "latency_ms": {s: {k: v for k, v in stats.items() if k != "all_ms"} for s, stats in lat_stats.items()},
    }

    prefix = "dryrun_" if dry_run else ""
    out_path = RESULTS_DIR / f"{prefix}retrieval_eval_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    latest = RESULTS_DIR / "latest_retrieval_eval.json"
    with open(latest, "w") as f:
        json.dump(payload, f, indent=2)

    log.info("Results saved → %s", out_path)
    log.info("           and → %s (latest)", latest)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def build_metrics_list(k_values: list[int]) -> list[str]:
    return [t.replace("{k}", str(k)) for t in METRICS_TEMPLATES for k in k_values]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate BM25 vs hybrid retrieval via the live /hybrid-search/ API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--api-url", default=DEFAULT_API_URL, help=f"FastAPI base URL (default: {DEFAULT_API_URL})")
    p.add_argument("--strategies", nargs="+", choices=["bm25", "hybrid"], default=DEFAULT_STRATEGIES)
    p.add_argument("--k", nargs="+", type=int, default=DEFAULT_K_VALUES, help="K values for metrics")
    p.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Candidates fetched per query (size= in request)")
    p.add_argument("--dry-run", action="store_true", help="Mock retrieval — no live API needed")
    return p.parse_args()


async def main_async(args: argparse.Namespace) -> None:

    # ── load dataset ──────────────────────────────────────────────────────────
    if not QRELS_PATH.exists() or not QUERIES_PATH.exists():
        log.error("Dataset not found. Run first:\n  python eval/build_eval_dataset.py")
        sys.exit(1)

    with open(QRELS_PATH) as f:
        qrels_raw: dict = json.load(f)
    with open(QUERIES_PATH) as f:
        queries: dict = json.load(f)

    total_rel = sum(len(v) for v in qrels_raw.values())
    log.info("Dataset: %d queries  |  %d total relevant docs", len(queries), total_rel)

    # ── API health check ──────────────────────────────────────────────────────
    if not args.dry_run:
        async with httpx.AsyncClient() as client:
            ok = False
            for path in ["/ping", "/health", "/"]:
                try:
                    r = await client.get(f"{args.api_url}{path}", timeout=5.0)
                    if r.status_code < 500:
                        ok = True
                        break
                except Exception:
                    continue
            if not ok:
                log.error("Cannot reach API at %s — use --dry-run or start the server", args.api_url)
                sys.exit(1)

    # ── run each strategy ─────────────────────────────────────────────────────
    runs: dict[str, Run] = {}
    lat_stats: dict[str, dict] = {}

    for strategy in args.strategies:
        run_dict, lats = await run_strategy(
            strategy=strategy,
            queries=queries,
            qrels_raw=qrels_raw,
            api_url=args.api_url,
            top_k=args.top_k,
            dry_run=args.dry_run,
        )
        runs[strategy] = Run(run_dict, name=strategy)
        lat_stats[strategy] = latency_stats(lats)

    # ── evaluate with ranx ────────────────────────────────────────────────────
    qrels_obj = Qrels(qrels_raw)
    metrics = build_metrics_list(args.k)

    report: dict[str, dict] = {s: evaluate(qrels_obj, run, metrics) for s, run in runs.items()}

    # ── print tables ──────────────────────────────────────────────────────────
    print_metrics_table(report, args.strategies, args.k)
    print_latency_table(lat_stats, args.strategies)
    print_delta_summary(report, lat_stats, args.strategies)

    # ranx statistical comparison when both strategies ran
    if len(runs) > 1:
        print("  ranx statistical comparison (p < 0.05)")
        print("─" * 55)
        try:
            print(compare(qrels_obj, list(runs.values()), metrics, max_p=0.05))
        except Exception as exc:
            log.warning("ranx compare() unavailable: %s", exc)

    # ── save ──────────────────────────────────────────────────────────────────
    save_results(report, lat_stats, args.strategies, args.k, args.api_url, args.dry_run)


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
