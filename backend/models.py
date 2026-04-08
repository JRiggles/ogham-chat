from dataclasses import dataclass


@dataclass
class ChatConfig:
    mode: str
    username: str
    host: str
    port: int
