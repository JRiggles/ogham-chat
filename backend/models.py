from dataclasses import dataclass


@dataclass
class ChatConfig:
    mode: str
    username: str
    host: str = '127.0.0.1'
    port: int = 9000
    relay_url: str | None = None
