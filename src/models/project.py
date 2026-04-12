"""
ORM models for the Projects feature.

Three models:
  Project             — a named workspace containing papers and conversations
  ProjectSource       — join row linking a project to a paper (any source)
  ProjectChatMessage  — persisted chat history scoped to a project
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.db.interfaces.postgresql import Base


class Project(Base):
    __tablename__ = "projects"

    __table_args__ = (
        Index("ix_projects_created_at", "created_at"),
        Index("ix_projects_updated_at", "updated_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # AI-generated overview of all sources in this project.
    # NULL until first generated. Regenerated when sources change.
    overview = Column(Text, nullable=True)
    overview_generated_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    sources = relationship(
        "ProjectSource",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="ProjectSource.added_at.desc()",
    )
    chat_messages = relationship(
        "ProjectChatMessage",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="ProjectChatMessage.created_at.asc()",
    )

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}')>"


class ProjectSource(Base):
    """
    Join table between a project and a paper.

    Intentionally source-agnostic — paper_id is the UUID (papers.id) which
    exists for both arxiv papers and user uploads. The papers.source column
    carries the distinction; this table doesn't need to repeat it.
    """

    __tablename__ = "project_sources"

    __table_args__ = (
        UniqueConstraint("project_id", "paper_id", name="uq_project_sources_project_paper"),
        Index("ix_project_sources_project_id", "project_id"),
        Index("ix_project_sources_paper_id", "paper_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    paper_id = Column(
        UUID(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    added_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    project = relationship("Project", back_populates="sources")
    paper = relationship("Paper", lazy="select")

    def __repr__(self):
        return f"<ProjectSource(project_id={self.project_id}, paper_id={self.paper_id})>"


class ProjectChatMessage(Base):
    """
    A single message in a project's chat history.

    Persisted so conversations survive page reloads — mirrors how
    NotebookLM keeps your conversation alongside your sources.
    """

    __tablename__ = "project_chat_messages"

    __table_args__ = (
        # Most common query: all messages for a project in order
        Index("ix_project_chat_messages_project_created", "project_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    # "user" or "assistant" — mirrors the OpenAI message role convention
    # already used in NvidiaClient
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    project = relationship("Project", back_populates="chat_messages")

    def __repr__(self):
        return f"<ProjectChatMessage(project_id={self.project_id}, role='{self.role}')>"
