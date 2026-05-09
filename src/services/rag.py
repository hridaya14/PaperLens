"""
Shared RAG service.

Pure service layer (no FastAPI imports).
Handles retrieval + LLM execution + streaming.
"""

import asyncio
import logging
import uuid as uuid_lib
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from src.repositories.project import ProjectRepository
from src.services.embeddings.nvidia_client import NIMEmbeddingsClient
from src.services.opensearch.client import OpenSearchClient

logger = logging.getLogger(__name__)

HISTORY_CONTEXT_LIMIT = 10


# ---------------------------------------------------------------------------
# Source URL resolution
# ---------------------------------------------------------------------------


def build_source_url(arxiv_id: str) -> str:
    try:
        uuid_lib.UUID(arxiv_id)
        return f"/api/v1/uploads/{arxiv_id}/pdf"
    except ValueError:
        clean_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
        return f"https://arxiv.org/pdf/{clean_id}.pdf"


# ---------------------------------------------------------------------------
# Project scoping
# ---------------------------------------------------------------------------


def resolve_paper_ids(
    project_id: Optional[uuid_lib.UUID],
    db: Session,
) -> Optional[List[str]]:
    if project_id is None:
        return None

    repo = ProjectRepository(db)
    project = repo.get_by_id(project_id)

    if not project:
        raise ValueError(f"Project '{project_id}' not found.")

    paper_ids = repo.get_paper_ids_for_project(project_id)

    if not paper_ids:
        raise ValueError(f"Project '{project_id}' has no sources.")

    logger.info(f"Project scoping: restricting search to {len(paper_ids)} papers")
    return paper_ids


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------


def build_context_query(query: str, history: List[Any]) -> str:
    if not history:
        return query

    lines = ["Previous conversation:"]
    for msg in history[-HISTORY_CONTEXT_LIMIT:]:
        prefix = "User" if msg.role == "user" else "Assistant"
        content = msg.content if len(msg.content) <= 300 else msg.content[:300] + "..."
        lines.append(f"{prefix}: {content}")

    lines.append(f"\nCurrent question: {query}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


async def prepare_chunks_and_sources(
    query: str,
    opensearch_client: OpenSearchClient,
    embeddings_service: NIMEmbeddingsClient,
    top_k: int = 10,
    use_hybrid: bool = True,
    categories: Optional[List[str]] = None,
    paper_ids: Optional[List[str]] = None,
) -> Tuple[List[Dict], List[str], str]:

    query_embedding = None
    search_mode = "bm25"

    if use_hybrid:
        try:
            query_embedding = await embeddings_service.embed_query(query)
            search_mode = "hybrid"
        except Exception as e:
            logger.warning(f"Embedding failed → fallback BM25: {e}")
            query_embedding = None
            search_mode = "bm25"

    logger.info(f"Retrieving top {top_k} chunks — mode={search_mode}, scoped={bool(paper_ids)}")

    # FIX: search_unified is a sync/blocking call. Run it in a thread pool so
    # it doesn't block the event loop while waiting on the OpenSearch network round trip.
    search_results = await asyncio.to_thread(
        opensearch_client.search_unified,
        query=query,
        query_embedding=query_embedding,
        size=top_k,
        from_=0,
        categories=categories,
        use_hybrid=use_hybrid and query_embedding is not None,
        min_score=0.0,
        paper_ids=paper_ids,
    )

    chunks: List[Dict] = []
    sources: List[str] = []
    seen_sources = set()

    for hit in search_results.get("hits", []):
        arxiv_id = hit.get("arxiv_id", "")

        chunks.append(
            {
                "arxiv_id": arxiv_id,
                "chunk_text": hit.get("chunk_text", hit.get("abstract", "")),
            }
        )

        if arxiv_id and arxiv_id not in seen_sources:
            seen_sources.add(arxiv_id)
            sources.append(build_source_url(arxiv_id))

    return chunks, sources, search_mode


# ---------------------------------------------------------------------------
# LLM execution (NON-STREAM)
# ---------------------------------------------------------------------------


async def run_rag_ask(
    context_query: str,
    chunks: List[Dict],
    model: str,
    nvidia_client: Any,
    save_message: Callable[[str, str], Any],
) -> Tuple[Dict[str, Any], Any]:
    """
    Async wrapper around the sync nvidia_client call.

    FIX: previously called synchronously inside async endpoints, blocking the
    event loop for the full LLM round trip (~14s). asyncio.to_thread() offloads
    the blocking HTTP call to a thread pool, freeing the loop for other requests.

    Returns:
        ({"answer": str, "metrics": {...}}, assistant_msg)
    """
    rag_response = await asyncio.to_thread(
        nvidia_client.generate_rag_answer,
        query=context_query,
        chunks=chunks,
        model=model,
    )

    if isinstance(rag_response, dict):
        answer = rag_response.get("answer", "Unable to generate answer.")
        metrics = rag_response.get("metrics") or {}
    else:
        answer = rag_response
        metrics = {}

    assistant_msg = save_message("assistant", answer)

    return {"answer": answer, "metrics": metrics}, assistant_msg


# ---------------------------------------------------------------------------
# LLM execution (STREAM)
# ---------------------------------------------------------------------------


async def iter_rag_stream(
    context_query: str,
    chunks: List[Dict],
    model: str,
    nvidia_client: Any,
    save_message: Callable[[str, str], Any],
) -> AsyncGenerator[Tuple[Optional[str], Optional[str], Any, Optional[Dict]], None]:
    """
    Async generator that offloads the blocking sync generator to a thread pool
    via a queue, so the event loop is never blocked between token yields.

    FIX: the previous sync generator called nvidia_client (a blocking HTTP
    stream) directly inside an async for loop, stalling the event loop on every
    chunk. The queue bridge below keeps the loop free — the thread feeds tokens
    in, the async generator drains them out.

    Yields:
      (text_chunk, None,          None,           None)     — streaming tokens
      (None,       full_response, assistant_msg,  metrics)  — final summary
    """
    full_response = ""
    final_metrics: Dict[str, Any] = {}
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _run_sync():
        try:
            for chunk in nvidia_client.generate_rag_answer_stream(
                query=context_query,
                chunks=chunks,
                model=model,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    # Run the blocking generator in a thread pool without awaiting it —
    # we drain the queue concurrently below.
    asyncio.get_event_loop().run_in_executor(None, _run_sync)

    while True:
        item = await queue.get()

        if item is None:
            # Sentinel — generator exhausted
            break

        if isinstance(item, Exception):
            raise item

        if item.get("response") is not None:
            text_chunk = item["response"]
            full_response += text_chunk
            yield text_chunk, None, None, None

        elif item.get("metrics") is not None:
            final_metrics = item["metrics"]

    assistant_msg = save_message("assistant", full_response)
    yield None, full_response, assistant_msg, final_metrics
