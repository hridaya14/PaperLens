"""
Repository for Project, ProjectSource, and ProjectChatMessage.

Follows the same pattern as PaperRepository — session injected in __init__,
methods return ORM objects or None, callers handle 404 logic.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload

from src.models.paper import Paper
from src.models.project import Project, ProjectChatMessage, ProjectSource

logger = logging.getLogger(__name__)


class ProjectRepository:
    def __init__(self, session: Session):
        self.session = session

    # -------------------------------------------------------------------------
    # Project CRUD
    # -------------------------------------------------------------------------

    def create(self, name: str, description: Optional[str] = None) -> Project:
        """Create a new empty project."""
        project = Project(name=name, description=description)
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        logger.info(f"Created project: id={project.id}, name='{project.name}'")
        return project

    def get_by_id(self, project_id: UUID) -> Optional[Project]:
        """Fetch a project by UUID. Returns None if not found."""
        stmt = select(Project).where(Project.id == project_id)
        return self.session.scalar(stmt)

    def get_all(self) -> List[Project]:
        """All projects ordered by most recently updated."""
        stmt = select(Project).order_by(Project.updated_at.desc())
        return list(self.session.scalars(stmt))

    def update(
        self,
        project: Project,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Project:
        """Update project name and/or description. Only non-None fields are changed."""
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        project.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(project)
        return project

    def delete(self, project: Project) -> None:
        """
        Hard-delete a project.

        ProjectSource and ProjectChatMessage rows cascade-delete automatically
        via their FK ondelete="CASCADE" — no manual cleanup needed.
        """
        self.session.delete(project)
        self.session.commit()
        logger.info(f"Deleted project: id={project.id}")

    def get_source_count(self, project_id: UUID) -> int:
        """Number of papers currently in a project."""
        stmt = select(func.count(ProjectSource.id)).where(
            ProjectSource.project_id == project_id
        )
        return self.session.scalar(stmt) or 0

    # -------------------------------------------------------------------------
    # Source management
    # -------------------------------------------------------------------------

    def get_sources_with_papers(self, project_id: UUID) -> List[ProjectSource]:
        """
        All ProjectSource rows for a project with Paper eagerly loaded.

        Ordered newest-first (most recently added at the top), matching
        how NotebookLM surfaces sources.
        """
        stmt = (
            select(ProjectSource)
            .where(ProjectSource.project_id == project_id)
            .options(joinedload(ProjectSource.paper))
            .order_by(ProjectSource.added_at.desc())
        )
        return list(self.session.scalars(stmt).unique())

    def get_source(self, project_id: UUID, paper_id: UUID) -> Optional[ProjectSource]:
        """Fetch a specific source row. Returns None if the paper isn't in the project."""
        stmt = select(ProjectSource).where(
            ProjectSource.project_id == project_id,
            ProjectSource.paper_id == paper_id,
        )
        return self.session.scalar(stmt)

    def source_exists(self, project_id: UUID, paper_id: UUID) -> bool:
        """Check whether a paper is already a source in this project."""
        return self.get_source(project_id, paper_id) is not None

    def add_source(self, project_id: UUID, paper_id: UUID) -> ProjectSource:
        """
        Add a paper to a project and bump project.updated_at.

        Raises IntegrityError if the paper is already in the project —
        callers should call source_exists() first for a clean 409.
        """
        source = ProjectSource(project_id=project_id, paper_id=paper_id)
        self.session.add(source)

        # Keep project.updated_at current so list ordering reflects activity
        project = self.get_by_id(project_id)
        if project:
            project.updated_at = datetime.now(timezone.utc)

        self.session.commit()
        self.session.refresh(source)
        logger.info(f"Added paper {paper_id} to project {project_id}")
        return source

    def remove_source(self, source: ProjectSource) -> None:
        """Remove a paper from a project and bump project.updated_at."""
        project = self.get_by_id(source.project_id)
        self.session.delete(source)

        if project:
            project.updated_at = datetime.now(timezone.utc)

        self.session.commit()
        logger.info(f"Removed paper {source.paper_id} from project {source.project_id}")

    def get_paper_ids_for_project(self, project_id: UUID) -> List[str]:
        """
        Flat list of paper UUID strings for a project.

        Used by the RAG layer to scope OpenSearch queries — passed as the
        paper_ids filter to search_unified().
        """
        stmt = select(ProjectSource.paper_id).where(
            ProjectSource.project_id == project_id
        )
        return [str(pid) for pid in self.session.scalars(stmt)]

    # -------------------------------------------------------------------------
    # Overview (AI-generated summary)
    # -------------------------------------------------------------------------

    def save_overview(self, project: Project, overview: str) -> Project:
        """Persist a freshly generated overview and record when it was made."""
        project.overview = overview
        project.overview_generated_at = datetime.now(timezone.utc)
        project.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(project)
        return project

    def clear_overview(self, project: Project) -> Project:
        """
        Invalidate the cached overview.

        Called when sources are added or removed so the next request
        triggers a fresh generation.
        """
        project.overview = None
        project.overview_generated_at = None
        self.session.commit()
        self.session.refresh(project)
        return project

    # -------------------------------------------------------------------------
    # Chat history
    # -------------------------------------------------------------------------

    def add_chat_message(
        self, project_id: UUID, role: str, content: str
    ) -> ProjectChatMessage:
        """Append a message to the project's chat history."""
        msg = ProjectChatMessage(project_id=project_id, role=role, content=content)
        self.session.add(msg)
        self.session.commit()
        self.session.refresh(msg)
        return msg

    def get_chat_history(
        self, project_id: UUID, limit: int = 50
    ) -> List[ProjectChatMessage]:
        """
        Return the most recent `limit` messages in chronological order.

        We fetch the last N by ordering descending then reversing, so
        the LLM always receives oldest-first context.
        """
        stmt = (
            select(ProjectChatMessage)
            .where(ProjectChatMessage.project_id == project_id)
            .order_by(ProjectChatMessage.created_at.desc())
            .limit(limit)
        )
        messages = list(self.session.scalars(stmt))
        messages.reverse()  # oldest first for LLM context
        return messages

    def clear_chat_history(self, project_id: UUID) -> int:
        """
        Delete all chat messages for a project.

        Returns the number of messages deleted.
        """
        stmt = select(ProjectChatMessage).where(
            ProjectChatMessage.project_id == project_id
        )
        messages = list(self.session.scalars(stmt))
        count = len(messages)
        for msg in messages:
            self.session.delete(msg)
        self.session.commit()
        logger.info(f"Cleared {count} chat messages for project {project_id}")
        return count
