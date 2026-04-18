from typing import Literal

from pydantic import BaseModel, Field


class ChatConfig(BaseModel):
    """Runtime chat configuration used by frontends and transports."""

    mode: Literal['host', 'join', 'relay']
    username: str = Field(min_length=1, max_length=64)
    host: str = '127.0.0.1'
    port: int = 9000
    relay_url: str | None = 'wss://ogham-chat.fastapicloud.dev/api/v1/ws'
    # optional current chat target; useful as you move away from broadcast
    peer: str | None = None
