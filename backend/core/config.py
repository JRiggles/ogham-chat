from typing import Literal

from pydantic import BaseModel

from backend.core.message import UsernameStr


class ChatConfig(BaseModel):
    """Runtime chat configuration used by frontends and transports."""

    mode: Literal['host', 'join', 'relay']
    requested_username: UsernameStr | None = None
    username: UsernameStr | None = None
    host: str = '127.0.0.1'
    port: int = 9000
    relay_url: str | None = 'wss://ogham-chat.fastapicloud.dev/api/v1/ws'
    onboarding_required: bool = False
    # optional current chat target; useful as you move away from broadcast
    peer: UsernameStr | None = None
