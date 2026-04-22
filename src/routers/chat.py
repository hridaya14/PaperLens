"""
Chat sessions router.

General (non-project) persistent chat with ChatGPT-style threading.

Endpoints:
  POST   /chat/sessions                         create a new session
  GET    /chat/sessions                         list all sessions
  GET    /chat/sessions/{id}                    session detail + messages
  PATCH  /chat/sessions/{id}                    rename session
  DELETE /chat/sessions/{id}                    delete session

  POST   /chat/sessions/{id}/ask                ask (persists to session)
  POST   /chat/sessions/{id}/stream             stream (persists to session)
  DELETE /chat/sessions/{id}/messages           clear messages (keep session)
"""

import json
import logging
import uuid as uuid_lib
from typing import List

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from src.dependencies import EmbeddingsDep, NvidiaDep, OpenSearchDep, SessionDep
from src.repositories.chat import ChatRepository
from src.schemas.api.chat import (
    ChatMessageResponse,
    ChatSessionDetailResponse,
    ChatSessionResponse,
    RenameSessionRequest,
    SessionAskRequest,
    SessionAskResponse,
)
from src.services.rag import build_context_query, iter_rag_stream, prepare_chunks_and_sources, run_rag_ask

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _get_session_or_404(repo: ChatRepository, session_id: str):
    try:
        sid = uuid_lib.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{session_id}' is not a valid UUID.")
    session = repo.get_session(sid)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    return session, sid


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(db: SessionDep) -> ChatSessionResponse:
    """Create a new empty chat session. Title is set from first message."""
    repo = ChatRepository(db)
    session = repo.create_session()
    return ChatSessionResponse(
        id=session.id,
        title=session.title,
        message_count=0,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get("/sessions", response_model=List[ChatSessionResponse])
def list_sessions(
    db: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> List[ChatSessionResponse]:
    """All sessions ordered by most recently active."""
    repo = ChatRepository(db)
    sessions = repo.get_all_sessions(limit=limit, offset=offset)
    return [
        ChatSessionResponse(
            id=s.id,
            title=s.title,
            message_count=repo.get_message_count(s.id),
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetailResponse)
def get_session(session_id: str, db: SessionDep) -> ChatSessionDetailResponse:
    """Full session with complete message history."""
    repo = ChatRepository(db)
    session, sid = _get_session_or_404(repo, session_id)
    messages = repo.get_messages(sid)
    return ChatSessionDetailResponse(
        id=session.id,
        title=session.title,
        messages=[
            ChatMessageResponse(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ],
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
def rename_session(session_id: str, body: RenameSessionRequest, db: SessionDep) -> ChatSessionResponse:
    repo = ChatRepository(db)
    session, sid = _get_session_or_404(repo, session_id)
    session = repo.rename_session(session, body.title)
    return ChatSessionResponse(
        id=session.id,
        title=session.title,
        message_count=repo.get_message_count(sid),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str, db: SessionDep) -> None:
    repo = ChatRepository(db)
    session, _ = _get_session_or_404(repo, session_id)
    repo.delete_session(session)


@router.delete("/sessions/{session_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
def clear_session_messages(session_id: str, db: SessionDep) -> None:
    """Clear all messages without deleting the session itself."""
    repo = ChatRepository(db)
    _, sid = _get_session_or_404(repo, session_id)
    repo.clear_messages(sid)


# ---------------------------------------------------------------------------
# Session RAG — ask
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/ask", response_model=SessionAskResponse)
async def session_ask(
    session_id: str,
    body: SessionAskRequest,
    db: SessionDep,
    opensearch: OpenSearchDep,
    embeddings_service: EmbeddingsDep,
    nvidia_client: NvidiaDep,
) -> SessionAskResponse:
    """
    RAG within a chat session. Searches the full index (no project scoping).
    Conversation history is included as LLM context. Both messages persisted.
    """
    repo = ChatRepository(db)
    session, sid = _get_session_or_404(repo, session_id)

    history = repo.get_recent_messages(sid, limit=10)
    context_query = build_context_query(body.query, history)

    chunks, sources, search_mode = await prepare_chunks_and_sources(
        query=context_query,
        opensearch_client=opensearch,
        embeddings_service=embeddings_service,
        top_k=body.top_k,
        use_hybrid=body.use_hybrid,
        categories=body.categories,
        paper_ids=None,  # global search — no project scoping
    )

    user_msg = repo.add_message(sid, role="user", content=body.query)

    if not chunks:
        answer = "I couldn't find any relevant information in the indexed papers to answer your question."
        assistant_msg = repo.add_message(sid, role="assistant", content=answer)
        return SessionAskResponse(
            query=body.query,
            answer=answer,
            sources=[],
            chunks_used=0,
            search_mode=search_mode,
            session_id=sid,
            user_message_id=user_msg.id,
            assistant_message_id=assistant_msg.id,
        )

    save_message = lambda role, content: repo.add_message(sid, role=role, content=content)
    answer, assistant_msg = run_rag_ask(context_query, chunks, body.model, nvidia_client, save_message)

    return SessionAskResponse(
        query=body.query,
        answer=answer,
        sources=sources,
        chunks_used=len(chunks),
        search_mode=search_mode,
        session_id=sid,
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg.id,
    )


# ---------------------------------------------------------------------------
# Session RAG — stream
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/stream")
async def session_stream(
    session_id: str,
    body: SessionAskRequest,
    db: SessionDep,
    opensearch: OpenSearchDep,
    embeddings_service: EmbeddingsDep,
    nvidia_client: NvidiaDep,
) -> StreamingResponse:
    """Streaming RAG within a session. Full response persisted once stream completes."""
    repo = ChatRepository(db)
    session, sid = _get_session_or_404(repo, session_id)

    history = repo.get_recent_messages(sid, limit=10)
    context_query = build_context_query(body.query, history)

    chunks, sources, search_mode = await prepare_chunks_and_sources(
        query=context_query,
        opensearch_client=opensearch,
        embeddings_service=embeddings_service,
        top_k=body.top_k,
        use_hybrid=body.use_hybrid,
        categories=body.categories,
        paper_ids=None,
    )

    user_msg = repo.add_message(sid, role="user", content=body.query)
    save_message = lambda role, content: repo.add_message(sid, role=role, content=content)

    async def generate_stream():
        if not chunks:
            answer = "I couldn't find any relevant information in the indexed papers."
            assistant_msg = save_message("assistant", answer)
            yield f"data: {json.dumps({'answer': answer, 'sources': [], 'done': True, 'user_message_id': str(user_msg.id), 'assistant_message_id': str(assistant_msg.id)})}\n\n"
            return

        yield f"data: {json.dumps({'sources': sources, 'chunks_used': len(chunks), 'search_mode': search_mode, 'session_id': str(sid), 'user_message_id': str(user_msg.id)})}\n\n"

        for text_chunk, full_response, assistant_msg in iter_rag_stream(
            context_query, chunks, body.model, nvidia_client, save_message
        ):
            if text_chunk is not None:
                yield f"data: {json.dumps({'chunk': text_chunk})}\n\n"
            elif full_response is not None:
                yield f"data: {json.dumps({'answer': full_response, 'done': True, 'assistant_message_id': str(assistant_msg.id)})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
