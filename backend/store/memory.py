from collections import deque
from datetime import datetime
from typing import Deque

from backend.core.message import ChatMessage


class MessageStore:
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
