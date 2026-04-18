from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Deque

from backend.core.message import ChatMessage
from backend.store.base import MessageStoreProtocol


class MemoryMessageStore(MessageStoreProtocol):
    """In-memory message store for local mode and lightweight testing."""

    def __init__(self, max_size: int = 10_000) -> None:
        """Initialize bounded in-memory storage for chat messages."""
        self._messages: Deque[ChatMessage] = deque(maxlen=max_size)

    def add(self, message: ChatMessage) -> None:
        """Append one message to the in-memory history buffer."""
        self._messages.append(message)

    def purge_expired(
        self,
        *,
        retention_days: int = 180,
        now: datetime | None = None,
    ) -> int:
        """Remove messages older than retention and return number deleted."""
        effective_now = self._normalize_timestamp(now or datetime.now(UTC))
        cutoff = effective_now - timedelta(days=retention_days)
        remaining_messages = deque(
            (
                message
                for message in self._messages
                if self._normalize_timestamp(message.created_at) > cutoff
            ),
            maxlen=self._messages.maxlen,
        )
        deleted_count = len(self._messages) - len(remaining_messages)
        self._messages = remaining_messages
        return deleted_count

    def _normalize_timestamp(self, created_at: datetime) -> datetime:
        """Convert naive or timezone-aware timestamps into UTC timestamps."""
        if created_at.tzinfo is None:
            return created_at.replace(tzinfo=UTC)
        return created_at.astimezone(UTC)

    def get_for_user(self, user_id: str) -> list[ChatMessage]:
        """Return all messages addressed to a specific user."""
        return [m for m in self._messages if m.to == user_id]

    def get_for_user_after(
        self, user_id: str, after: datetime | None = None
    ) -> list[ChatMessage]:
        """Return user-directed messages newer than an optional timestamp."""
        results: list[ChatMessage] = []
        for message in self._messages:
            if message.to != user_id:
                continue
            if after is not None and message.created_at <= after:
                continue
            results.append(message)
        return results

    def get_conversation(
        self,
        user_id: str,
        peer_id: str,
        after: datetime | None = None,
    ) -> list[ChatMessage]:
        """Return ordered direct messages exchanged between two users."""
        results: list[ChatMessage] = []
        for message in self._messages:
            is_conversation_message = (
                message.sender == user_id and message.to == peer_id
            ) or (message.sender == peer_id and message.to == user_id)
            if not is_conversation_message:
                continue
            if after is not None and message.created_at <= after:
                continue
            results.append(message)
        return results
