"""
Shared RAG service.

Extracted from ask.py so that the projects router, the chat sessions router,
and the legacy /ask endpoint all use identical retrieval and execution logic.

Nothing in here imports from FastAPI — pure service code.
"""

import logging
import uuid as uuid_lib
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from sqlalchemy.orm import Session
from src.repositories.project import ProjectRepository
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.embeddings.nvidia_client import NIMEmbeddingsClient
from src.services.opensearch.client import OpenSearchClient

logger = logging.getLogger(__name__)

# How many recent messages to include as conversation context for the LLM.
HISTORY_CONTEXT_LIMIT = 10


# ---------------------------------------------------------------------------
# Source URL resolution
# ---------------------------------------------------------------------------


def build_source_url(arxiv_id: str) -> str:
    """
    Return the correct PDF URL for a chunk's arxiv_id field.

    arxiv papers  → public arxiv PDF URL
    user uploads  → local serve endpoint (arxiv_id field contains a UUID string)

    The distinction is reliable: real arxiv IDs (e.g. "2401.12345") never
    parse as valid UUIDs.
    """
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
    """
    Return paper UUID strings for a project, or None for global search.

    Raises ValueError if the project doesn't exist or has no sources.
    Callers convert this to HTTPException with the appropriate status code.
    """
    if project_id is None:
        return None

    repo = ProjectRepository(db)
    project = repo.get_by_id(project_id)

    if not project:
        raise ValueError(f"Project '{project_id}' not found.")

    paper_ids = repo.get_paper_ids_for_project(project_id)

    if not paper_ids:
        raise ValueError(f"Project '{project_id}' has no sources. Add papers to the project before querying.")

    logger.info(f"Project scoping: restricting search to {len(paper_ids)} papers")
    return paper_ids


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------


def build_context_query(query: str, history: List[Any]) -> str:
    """
    Prepend recent conversation history to the user query.

    Works with both ProjectChatMessage and ChatMessage ORM objects — both
    have .role and .content. Returns the query unchanged when history is empty.
    """
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
# Core retrieval
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
    """
    Core RAG retrieval — fetch chunks from OpenSearch and build source URLs.

    Returns (chunks, sources, search_mode).
    """
    query_embedding = None
    search_mode = "bm25"

    if use_hybrid:
        try:
            query_embedding = await embeddings_service.embed_query(query)
            search_mode = "hybrid"
        except Exception as e:
            logger.warning(f"Embedding failed, falling back to BM25: {e}")
            query_embedding = None
            search_mode = "bm25"

    logger.info(f"Retrieving top {top_k} chunks — mode={search_mode}, scoped={bool(paper_ids)}")

    search_results = opensearch_client.search_unified(
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
    seen_sources: set = set()
    sources: List[str] = []

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
# LLM execution — shared between ask and stream routers
# ---------------------------------------------------------------------------


def run_rag_ask(
    context_query: str,
    chunks: List[Dict],
    model: str,
    nvidia_client: Any,
    save_message: Callable[[str, str], Any],
) -> Tuple[str, Any]:
    """
    Execute a non-streaming LLM RAG call and persist the assistant response.

    :param context_query: Query string (may include prepended history)
    :param chunks: Retrieved chunks from OpenSearch
    :param model: LLM model identifier
    :param nvidia_client: NvidiaClient instance
    :param save_message: Callable(role, content) → persisted message ORM object.
                         Abstracts over ProjectRepository.add_chat_message and
                         ChatRepository.add_message so this function stays
                         repo-agnostic.
    :returns: (answer_text, assistant_message_orm)
    """
    rag_response = nvidia_client.generate_rag_answer(query=context_query, chunks=chunks, model=model)
    answer = rag_response.get("answer", "Unable to generate answer.")
    assistant_msg = save_message("assistant", answer)
    return answer, assistant_msg


def iter_rag_stream(
    context_query: str,
    chunks: List[Dict],
    model: str,
    nvidia_client: Any,
    save_message: Callable[[str, str], Any],
) -> Generator[Tuple[Optional[str], Optional[str], Any], None, None]:
    """
    Sync generator that drives the streaming LLM call and persists the result.

    Yields two kinds of tuples:
      (text_chunk, None,          None)          — for each token received
      (None,       full_response, assistant_msg) — once, when stream is done

    Using a sync generator (not async) because NvidiaClient.generate_rag_answer_stream
    returns a plain Generator. Routers iterate this with a regular `for` loop
    inside their async `generate_stream` function — FastAPI handles the mix correctly.

    :param save_message: Callable(role, content) → persisted message ORM object.
    """
    full_response = ""

    for chunk in nvidia_client.generate_rag_answer_stream(query=context_query, chunks=chunks, model=model):
        if chunk.get("response"):
            text_chunk = chunk["response"]
            full_response += text_chunk
            yield text_chunk, None, None

        if chunk.get("done", False):
            assistant_msg = save_message("assistant", full_response)
            yield None, full_response, assistant_msg
            break
