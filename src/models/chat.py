"""
ORM models for general (non-project) chat sessions.

Two models:
  ChatSession  — a named conversation thread (like a ChatGPT sidebar item)
  ChatMessage  — a single message within a session

Project chat uses ProjectChatMessage (src/models/project.py) which is a
single thread per project. This module is for the global, session-based chat.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.db.interfaces.postgresql import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    __table_args__ = (
        # Most common query: list all sessions newest first
        Index("ix_chat_sessions_updated_at", "updated_at"),
        Index("ix_chat_sessions_created_at", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Auto-derived from the first user message (first ~60 chars).
    # NULL on creation, set on first message — same pattern as ChatGPT.
    title = Column(String(255), nullable=True)

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

    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="ChatMessage.created_at.asc()",
    )

    def __repr__(self):
        return f"<ChatSession(id={self.id}, title='{self.title}')>"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    __table_args__ = (
        # Fetch all messages for a session in order — the most common query
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # "user" | "assistant" — same convention as ProjectChatMessage and NvidiaClient
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage(session_id={self.session_id}, role='{self.role}')>"
