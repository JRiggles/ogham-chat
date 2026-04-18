from datetime import datetime
from typing import Protocol

from backend.core.message import ChatMessage


class MessageStoreProtocol(Protocol):
    """Contract implemented by chat message persistence backends."""

    def add(self, message: ChatMessage) -> None:
        """Persist one chat message."""

    def get_for_user(self, user_id: str) -> list[ChatMessage]:
        """Return all messages addressed to a specific user."""

    def purge_expired(
        self,
        *,
        retention_days: int = 180,
        now: datetime | None = None,
    ) -> int:
        """Delete expired messages and return the number removed."""

    def get_for_user_after(
        self, user_id: str, after: datetime | None = None
    ) -> list[ChatMessage]:
        """Return user-directed messages newer than an optional timestamp."""

    def get_conversation(
        self,
        user_id: str,
        peer_id: str,
        after: datetime | None = None,
    ) -> list[ChatMessage]:
        """Return ordered direct messages exchanged between two users."""
