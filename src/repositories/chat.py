"""
Repository for ChatSession and ChatMessage.

Handles all DB operations for general (non-project) chat threads.
Project chat history is handled by ProjectRepository.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from src.models.chat import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

# How many characters from the first user message to use as the session title
_TITLE_MAX_CHARS = 60


def _derive_title(first_user_message: str) -> str:
    """
    Derive a session title from the first user message.

    Truncates at the last word boundary before _TITLE_MAX_CHARS so we
    never cut mid-word, then appends ellipsis if truncated.
    """
    text = first_user_message.strip()
    if len(text) <= _TITLE_MAX_CHARS:
        return text
    truncated = text[:_TITLE_MAX_CHARS].rsplit(" ", 1)[0]
    return f"{truncated}..."


class ChatRepository:
    def __init__(self, session: Session):
        self.session = session

    # -------------------------------------------------------------------------
    # Session CRUD
    # -------------------------------------------------------------------------

    def create_session(self) -> ChatSession:
        """
        Create a new empty chat session with no title.

        Title is set automatically when the first message is saved
        via add_message() — no separate call required.
        """
        chat_session = ChatSession()
        self.session.add(chat_session)
        self.session.commit()
        self.session.refresh(chat_session)
        logger.info(f"Created chat session: id={chat_session.id}")
        return chat_session

    def get_session(self, session_id: UUID) -> Optional[ChatSession]:
        """Fetch a session by UUID. Returns None if not found."""
        stmt = select(ChatSession).where(ChatSession.id == session_id)
        return self.session.scalar(stmt)

    def get_all_sessions(self, limit: int = 50, offset: int = 0) -> List[ChatSession]:
        """
        All sessions ordered by most recently active (updated_at desc).

        Mirrors the ChatGPT sidebar behaviour — most recent conversation
        at the top. Default limit of 50 covers all practical cases for
        a single-user platform.
        """
        stmt = (
            select(ChatSession)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt))

    def get_session_count(self) -> int:
        """Total number of chat sessions."""
        return self.session.scalar(select(func.count(ChatSession.id))) or 0

    def rename_session(self, chat_session: ChatSession, title: str) -> ChatSession:
        """Manually rename a session — user-initiated rename."""
        chat_session.title = title.strip()[:255]
        chat_session.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(chat_session)
        return chat_session

    def delete_session(self, chat_session: ChatSession) -> None:
        """
        Hard-delete a session.

        ChatMessage rows cascade-delete automatically via the FK.
        """
        self.session.delete(chat_session)
        self.session.commit()
        logger.info(f"Deleted chat session: id={chat_session.id}")

    # -------------------------------------------------------------------------
    # Message operations
    # -------------------------------------------------------------------------

    def add_message(
        self,
        session_id: UUID,
        role: str,
        content: str,
    ) -> ChatMessage:
        """
        Append a message to a session.

        Also:
          - Sets the session title from the first user message if not yet set
          - Bumps session.updated_at so the list ordering stays current
        """
        msg = ChatMessage(session_id=session_id, role=role, content=content)
        self.session.add(msg)

        # Update session metadata
        chat_session = self.get_session(session_id)
        if chat_session:
            # Auto-title from first user message
            if chat_session.title is None and role == "user":
                chat_session.title = _derive_title(content)

            chat_session.updated_at = datetime.now(timezone.utc)

        self.session.commit()
        self.session.refresh(msg)
        return msg

    def get_messages(
        self,
        session_id: UUID,
        limit: int = 100,
    ) -> List[ChatMessage]:
        """
        All messages for a session in chronological order (oldest first).

        limit=100 is generous for a single-user platform. The route layer
        can expose this as a query param if needed later.
        """
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def get_recent_messages(
        self,
        session_id: UUID,
        limit: int = 20,
    ) -> List[ChatMessage]:
        """
        The most recent `limit` messages in chronological order.

        Used to build LLM conversation context — we send the last N
        messages rather than the full history to stay within token limits.
        Fetches descending then reverses so the LLM receives oldest-first.
        """
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        messages = list(self.session.scalars(stmt))
        messages.reverse()
        return messages

    def get_message_count(self, session_id: UUID) -> int:
        """Number of messages in a session."""
        stmt = select(func.count(ChatMessage.id)).where(
            ChatMessage.session_id == session_id
        )
        return self.session.scalar(stmt) or 0

    def clear_messages(self, session_id: UUID) -> int:
        """
        Delete all messages in a session without deleting the session itself.

        Returns number of messages deleted. Resets the session title so
        the next message triggers auto-titling again.
        """
        stmt = select(ChatMessage).where(ChatMessage.session_id == session_id)
        messages = list(self.session.scalars(stmt))
        count = len(messages)

        for msg in messages:
            self.session.delete(msg)

        # Reset title so auto-titling fires again on next message
        chat_session = self.get_session(session_id)
        if chat_session:
            chat_session.title = None
            chat_session.updated_at = datetime.now(timezone.utc)

        self.session.commit()
        logger.info(f"Cleared {count} messages from session {session_id}")
        return count
