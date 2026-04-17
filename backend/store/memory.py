from collections import deque
from datetime import datetime
from typing import Deque

from backend.core.message import ChatMessage
from backend.store.base import MessageStoreProtocol


class MemoryMessageStore(MessageStoreProtocol):
    def __init__(self, max_size: int = 10_000) -> None:
        self._messages: Deque[ChatMessage] = deque(maxlen=max_size)

    def add(self, message: ChatMessage) -> None:
        self._messages.append(message)

    def get_for_user(self, user_id: str) -> list[ChatMessage]:
        return [m for m in self._messages if m.to == user_id]

    def get_for_user_after(
        self, user_id: str, after: datetime | None = None
    ) -> list[ChatMessage]:
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
        results: list[ChatMessage] = []
        for message in self._messages:
            is_conversation_message = (
                (message.sender == user_id and message.to == peer_id)
                or (message.sender == peer_id and message.to == user_id)
            )
            if not is_conversation_message:
                continue
            if after is not None and message.created_at <= after:
                continue
            results.append(message)
        return results
