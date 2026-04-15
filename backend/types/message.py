from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

SenderStr = Annotated[str, Field(min_length=1, max_length=64)]
MessageTextStr = Annotated[str, Field(min_length=1, max_length=4096)]


class ChatMessage(BaseModel):
    id: UUID
    sender: SenderStr
    text: MessageTextStr
    created_at: datetime
    is_system: bool = False
