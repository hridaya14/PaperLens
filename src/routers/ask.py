import json
import logging
import uuid as uuid_lib
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from src.dependencies import EmbeddingsDep, NvidiaDep, OpenSearchDep, SessionDep
from src.repositories.project import ProjectRepository
from src.schemas.api.ask import AskRequest, AskResponse

logger = logging.getLogger(__name__)

ask_router = APIRouter(tags=["ask"])
stream_router = APIRouter(tags=["stream"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_source_url(arxiv_id: str) -> str:
    """
    Build the correct source URL from a chunk's arxiv_id field.

    For arxiv papers:   arxiv_id is a real arxiv ID  → return arxiv PDF URL
    For user uploads:   arxiv_id is a UUID string    → return local serve URL

    The distinction is reliable because real arxiv IDs never parse as UUIDs.
    """
    try:
        uuid_lib.UUID(arxiv_id)
        # Parsed as UUID → this is a user upload
        return f"/api/v1/uploads/{arxiv_id}/pdf"
    except ValueError:
        # Not a UUID → real arxiv ID
        clean_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
        return f"https://arxiv.org/pdf/{clean_id}.pdf"


async def _resolve_paper_ids(
    project_id: Optional[uuid_lib.UUID],
    db,
) -> Optional[List[str]]:
    """
    If a project_id is given, return the list of paper UUID strings for that project.
    Returns None when no project scoping is requested (search entire index).
    Raises HTTPException if the project doesn't exist or has no sources.
    """
    if project_id is None:
        return None

    repo = ProjectRepository(db)
    project = repo.get_by_id(project_id)

    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    paper_ids = repo.get_paper_ids_for_project(project_id)

    if not paper_ids:
        raise HTTPException(
            status_code=422,
            detail=f"Project '{project_id}' has no sources. Add papers to the project before querying.",
        )

    logger.info(f"Project '{project_id}' scoping active — restricting search to {len(paper_ids)} papers")
    return paper_ids


async def _prepare_chunks_and_sources(
    request: AskRequest,
    opensearch_client,
    embeddings_service,
    db,
):
    """Shared retrieval function for both ask and stream endpoints."""

    # ---- Resolve project scoping ----
    paper_ids = await _resolve_paper_ids(request.project_id, db)

    # ---- Generate query embedding for hybrid search ----
    query_embedding = None
    search_mode = "bm25"

    if request.use_hybrid:
        try:
            query_embedding = await embeddings_service.embed_query(request.query)
            search_mode = "hybrid"
            logger.info("Generated query embedding for hybrid search")
        except Exception as e:
            logger.warning(f"Failed to generate embeddings, falling back to BM25: {e}")
            query_embedding = None
            search_mode = "bm25"

    # ---- Retrieve top-k chunks (scoped to project if paper_ids provided) ----
    logger.info(f"Retrieving top {request.top_k} chunks for query: '{request.query}'")

    search_results = opensearch_client.search_unified(
        query=request.query,
        query_embedding=query_embedding,
        size=request.top_k,
        from_=0,
        categories=request.categories,
        use_hybrid=request.use_hybrid and query_embedding is not None,
        min_score=0.0,
        paper_ids=paper_ids,  # None = global search; list = project-scoped
    )

    # ---- Build chunks and deduplicated source URLs ----
    chunks = []
    seen_sources = set()
    sources = []

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
            sources.append(_build_source_url(arxiv_id))

    return chunks, sources, search_mode


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@ask_router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    opensearch_client: OpenSearchDep,
    embeddings_service: EmbeddingsDep,
    nvidia_client: NvidiaDep,
    db: SessionDep,
) -> AskResponse:
    """
    RAG question answering endpoint.

    When project_id is set in the request body, retrieval is restricted to
    papers in that project. When omitted, the entire index is searched.
    """
    try:
        if not opensearch_client.health_check():
            raise HTTPException(status_code=503, detail="Search service is currently unavailable")

        try:
            nvidia_client.health_check()
        except Exception as e:
            logger.error(f"LLM service unavailable: {e}")
            raise HTTPException(status_code=503, detail="LLM service is currently unavailable")

        chunks, sources, search_mode = await _prepare_chunks_and_sources(request, opensearch_client, embeddings_service, db)

        if not chunks:
            return AskResponse(
                query=request.query,
                answer="I couldn't find any relevant information in the papers to answer your question.",
                sources=[],
                chunks_used=0,
                search_mode=search_mode,
                project_id=request.project_id,
            )

        logger.info(f"Retrieved {len(chunks)} chunks, generating answer with {request.model}")

        rag_response = nvidia_client.generate_rag_answer(query=request.query, chunks=chunks, model=request.model)

        return AskResponse(
            query=request.query,
            answer=rag_response.get("answer", "Unable to generate answer"),
            sources=sources,
            chunks_used=len(chunks),
            search_mode=search_mode,
            project_id=request.project_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in ask endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process question: {str(e)}")


@stream_router.post("/stream")
async def ask_question_stream(
    request: AskRequest,
    opensearch_client: OpenSearchDep,
    embeddings_service: EmbeddingsDep,
    nvidia_client: NvidiaDep,
    db: SessionDep,
) -> StreamingResponse:
    """
    Streaming RAG endpoint.

    Supports project scoping via project_id in the request body — identical
    behaviour to /ask but streams the answer token by token.
    """

    async def generate_stream():
        try:
            if not opensearch_client.health_check():
                yield f"data: {json.dumps({'error': 'Search service unavailable'})}\n\n"
                return

            nvidia_client.health_check()

            chunks, sources, search_mode = await _prepare_chunks_and_sources(request, opensearch_client, embeddings_service, db)

            if not chunks:
                yield f"data: {json.dumps({'answer': 'No relevant information found.', 'sources': [], 'done': True})}\n\n"
                return

            # Send metadata first (sources, chunk count, search mode, project scope)
            yield f"data: {json.dumps({'sources': sources, 'chunks_used': len(chunks), 'search_mode': search_mode, 'project_id': str(request.project_id) if request.project_id else None})}\n\n"

            # Stream the answer
            full_response = ""
            async for chunk in nvidia_client.generate_rag_answer_stream(query=request.query, chunks=chunks, model=request.model):
                if chunk.get("response"):
                    text_chunk = chunk["response"]
                    full_response += text_chunk
                    yield f"data: {json.dumps({'chunk': text_chunk})}\n\n"

                if chunk.get("done", False):
                    yield f"data: {json.dumps({'answer': full_response, 'done': True})}\n\n"
                    break

        except HTTPException as e:
            yield f"data: {json.dumps({'error': e.detail})}\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
