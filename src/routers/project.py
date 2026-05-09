"""
Projects router.

Endpoints:
  POST   /projects                              create project
  GET    /projects                              list projects
  GET    /projects/{id}                         detail + sources
  PATCH  /projects/{id}                         rename / update description
  DELETE /projects/{id}                         delete project

  POST   /projects/{id}/sources                 add paper to project
  DELETE /projects/{id}/sources/{paper_id}      remove paper from project

  GET    /projects/{id}/chat                    get project chat history
  DELETE /projects/{id}/chat                    clear project chat history
  POST   /projects/{id}/ask                     project-scoped RAG (persists to chat)
  POST   /projects/{id}/stream                  project-scoped streaming RAG (persists to chat)
"""

import json
import logging
import uuid as uuid_lib

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from src.dependencies import EmbeddingsDep, NvidiaDep, OpenSearchDep, SessionDep
from src.repositories.paper import PaperRepository
from src.repositories.project import ProjectRepository
from src.schemas.api.project import (
    AddSourceRequest,
    AddSourceResponse,
    ProjectAskRequest,
    ProjectAskResponse,
    ProjectChatHistoryResponse,
    ProjectChatMessageResponse,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectPaperSummary,
    ProjectResponse,
    ProjectUpdate,
)
from src.services.rag import (
    build_context_query,
    iter_rag_stream,
    prepare_chunks_and_sources,
    resolve_paper_ids,
    run_rag_ask,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_project_or_404(repo: ProjectRepository, project_id: str):
    try:
        pid = uuid_lib.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{project_id}' is not a valid UUID.")
    project = repo.get_by_id(pid)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return project, pid


def _build_paper_summary(source) -> ProjectPaperSummary:
    paper = source.paper
    return ProjectPaperSummary(
        id=paper.id,
        source=paper.source,
        arxiv_id=paper.arxiv_id,
        original_filename=paper.original_filename,
        title=paper.title,
        authors=paper.authors if isinstance(paper.authors, list) else [],
        abstract=paper.abstract,
        categories=paper.categories if isinstance(paper.categories, list) else [],
        published_date=paper.published_date,
        pdf_processed=paper.pdf_processed,
        added_at=source.added_at,
    )


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, db: SessionDep) -> ProjectResponse:
    repo = ProjectRepository(db)
    project = repo.create(name=body.name, description=body.description)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        overview=project.overview,
        source_count=0,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("", response_model=list[ProjectResponse])
def list_projects(db: SessionDep) -> list[ProjectResponse]:
    repo = ProjectRepository(db)
    projects = repo.get_all()
    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            overview=p.overview,
            source_count=repo.get_source_count(p.id),
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project(project_id: str, db: SessionDep) -> ProjectDetailResponse:
    repo = ProjectRepository(db)
    project, pid = _get_project_or_404(repo, project_id)
    sources = repo.get_sources_with_papers(pid)
    return ProjectDetailResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        overview=project.overview,
        overview_generated_at=project.overview_generated_at,
        sources=[_build_paper_summary(s) for s in sources],
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, body: ProjectUpdate, db: SessionDep) -> ProjectResponse:
    repo = ProjectRepository(db)
    project, pid = _get_project_or_404(repo, project_id)
    project = repo.update(project, name=body.name, description=body.description)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        overview=project.overview,
        source_count=repo.get_source_count(pid),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: SessionDep) -> None:
    repo = ProjectRepository(db)
    project, _ = _get_project_or_404(repo, project_id)
    repo.delete(project)


# ---------------------------------------------------------------------------
# Source management
# ---------------------------------------------------------------------------


@router.post("/{project_id}/sources", response_model=AddSourceResponse, status_code=status.HTTP_201_CREATED)
def add_source(project_id: str, body: AddSourceRequest, db: SessionDep) -> AddSourceResponse:
    repo = ProjectRepository(db)
    paper_repo = PaperRepository(db)
    project, pid = _get_project_or_404(repo, project_id)

    paper = paper_repo.get_by_id(body.paper_id)
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Paper '{body.paper_id}' not found.")

    if repo.source_exists(pid, body.paper_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Paper '{body.paper_id}' is already in this project.")

    try:
        source = repo.add_source(project_id=pid, paper_id=body.paper_id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Paper is already in this project.")

    repo.clear_overview(project)
    source.paper = paper

    return AddSourceResponse(
        project_id=pid,
        paper_id=body.paper_id,
        added_at=source.added_at,
        paper=_build_paper_summary(source),
    )


@router.delete("/{project_id}/sources/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_source(project_id: str, paper_id: str, db: SessionDep) -> None:
    repo = ProjectRepository(db)
    project, pid = _get_project_or_404(repo, project_id)

    try:
        paper_uuid = uuid_lib.UUID(paper_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{paper_id}' is not a valid UUID.")

    source = repo.get_source(pid, paper_uuid)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Paper '{paper_id}' is not in project '{project_id}'.")

    repo.remove_source(source)
    repo.clear_overview(project)


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------


@router.get("/{project_id}/chat", response_model=ProjectChatHistoryResponse)
def get_project_chat(project_id: str, db: SessionDep) -> ProjectChatHistoryResponse:
    repo = ProjectRepository(db)
    _, pid = _get_project_or_404(repo, project_id)
    messages = repo.get_chat_history(pid, limit=200)
    return ProjectChatHistoryResponse(
        project_id=pid,
        messages=[
            ProjectChatMessageResponse(
                id=m.id,
                project_id=m.project_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.delete("/{project_id}/chat", status_code=status.HTTP_204_NO_CONTENT)
def clear_project_chat(project_id: str, db: SessionDep) -> None:
    repo = ProjectRepository(db)
    _, pid = _get_project_or_404(repo, project_id)
    repo.clear_chat_history(pid)


# ---------------------------------------------------------------------------
# Project-scoped RAG — ask
# ---------------------------------------------------------------------------


@router.post("/{project_id}/ask", response_model=ProjectAskResponse)
async def project_ask(
    project_id: str,
    body: ProjectAskRequest,
    db: SessionDep,
    opensearch: OpenSearchDep,
    embeddings_service: EmbeddingsDep,
    nvidia_client: NvidiaDep,
) -> ProjectAskResponse:
    """
    Project-scoped RAG. Retrieval restricted to project papers.
    User message and assistant response are both persisted to the project thread.
    """
    repo = ProjectRepository(db)
    project, pid = _get_project_or_404(repo, project_id)

    try:
        paper_ids = resolve_paper_ids(pid, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    history = repo.get_chat_history(pid, limit=10)
    context_query = build_context_query(body.query, history)

    chunks, sources, search_mode = await prepare_chunks_and_sources(
        query=context_query,
        opensearch_client=opensearch,
        embeddings_service=embeddings_service,
        top_k=body.top_k,
        use_hybrid=body.use_hybrid,
        categories=body.categories,
        paper_ids=paper_ids,
    )

    user_msg = repo.add_chat_message(pid, role="user", content=body.query)

    if not chunks:
        answer = "I couldn't find any relevant information in this project's papers to answer your question."
        assistant_msg = repo.add_chat_message(pid, role="assistant", content=answer)
        return ProjectAskResponse(
            query=body.query,
            answer=answer,
            sources=[],
            chunks_used=0,
            search_mode=search_mode,
            project_id=pid,
            user_message_id=user_msg.id,
            assistant_message_id=assistant_msg.id,
            metrics={},
        )

    save_message = lambda role, content: repo.add_chat_message(pid, role=role, content=content)
    result, assistant_msg = await run_rag_ask(context_query, chunks, body.model, nvidia_client, save_message)

    return ProjectAskResponse(
        query=body.query,
        answer=result["answer"],
        sources=sources,
        chunks_used=len(chunks),
        search_mode=search_mode,
        project_id=pid,
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg.id,
        metrics=result.get("metrics", {}),
    )


# ---------------------------------------------------------------------------
# Project-scoped RAG — stream
# ---------------------------------------------------------------------------


@router.post("/{project_id}/stream")
async def project_stream(
    project_id: str,
    body: ProjectAskRequest,
    db: SessionDep,
    opensearch: OpenSearchDep,
    embeddings_service: EmbeddingsDep,
    nvidia_client: NvidiaDep,
) -> StreamingResponse:
    """
    Project-scoped streaming RAG. Full response persisted once stream completes.
    """
    repo = ProjectRepository(db)
    project, pid = _get_project_or_404(repo, project_id)

    try:
        paper_ids = resolve_paper_ids(pid, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    history = repo.get_chat_history(pid, limit=10)
    context_query = build_context_query(body.query, history)

    chunks, sources, search_mode = await prepare_chunks_and_sources(
        query=context_query,
        opensearch_client=opensearch,
        embeddings_service=embeddings_service,
        top_k=body.top_k,
        use_hybrid=body.use_hybrid,
        categories=body.categories,
        paper_ids=paper_ids,
    )

    user_msg = repo.add_chat_message(pid, role="user", content=body.query)
    save_message = lambda role, content: repo.add_chat_message(pid, role=role, content=content)

    async def generate_stream():
        if not chunks:
            answer = "I couldn't find any relevant information in this project's papers."
            assistant_msg = save_message("assistant", answer)
            yield f"data: {json.dumps({'answer': answer, 'sources': [], 'done': True, 'metrics': {}, 'user_message_id': str(user_msg.id), 'assistant_message_id': str(assistant_msg.id)})}\n\n"
            return

        yield f"data: {json.dumps({'sources': sources, 'chunks_used': len(chunks), 'search_mode': search_mode, 'project_id': str(pid), 'user_message_id': str(user_msg.id)})}\n\n"

        async for text_chunk, full_response, assistant_msg, metrics in iter_rag_stream(
            context_query, chunks, body.model, nvidia_client, save_message
        ):
            if text_chunk is not None:
                yield f"data: {json.dumps({'chunk': text_chunk})}\n\n"
            elif full_response is not None:
                yield f"data: {json.dumps({'answer': full_response, 'done': True, 'metrics': metrics or {}, 'assistant_message_id': str(assistant_msg.id)})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
