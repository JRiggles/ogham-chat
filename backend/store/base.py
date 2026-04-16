from datetime import datetime
from typing import Protocol

from backend.core.message import ChatMessage


class MessageStoreProtocol(Protocol):
    def add(self, message: ChatMessage) -> None: ...

    def get_for_user(self, user_id: str) -> list[ChatMessage]: ...

    def get_for_user_after(
        self, user_id: str, after: datetime | None = None
    ) -> list[ChatMessage]: ...
