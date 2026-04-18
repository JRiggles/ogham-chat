from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field

UsernameStr = Annotated[str, Field(min_length=1, max_length=64)]
MessageContentStr = Annotated[str, Field(min_length=1, max_length=4096)]


class ChatMessage(BaseModel):
    """Canonical chat message exchanged between clients and server APIs."""

    message_id: UUID
    sender: UsernameStr
    to: UsernameStr
    content: MessageContentStr
    created_at: datetime
    is_system: bool = False
    metadata: dict[str, Any] | None = None


class MessageEnvelope(BaseModel):
    """Transport envelope wrapper containing packet type and payload."""

    type: str
    data: dict[str, Any]
