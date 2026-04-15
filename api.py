from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.types import ChatMessage, MessageTextStr, SenderStr

app = FastAPI(title='Ogham Chat API', version='0.1.0')
v1 = APIRouter(prefix='/api/v1', tags=['v1'])


class MessageIn(BaseModel):
    sender: SenderStr
    text: MessageTextStr


class MessageOut(BaseModel):
    id: UUID
    sender: str
    text: str  # TODO: cryptographically secure message format
    created_at: datetime


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for connection in self._connections:
            try:
                await connection.send_json(payload)
            except RuntimeError:
                stale.append(connection)

        for connection in stale:
            self.disconnect(connection)

    @property
    def active_count(self) -> int:
        return len(self._connections)


messages: list[ChatMessage] = []
ws_manager = ConnectionManager()


def to_message_out(message: ChatMessage) -> MessageOut:
    return MessageOut(
        id=message.id,
        sender=message.sender,
        text=message.text,
        created_at=message.created_at,
    )


@v1.get('/')
async def root() -> dict[str, str]:
    return {'service': 'ogham-chat-api', 'status': 'ok'}


@v1.get('/health')
async def health() -> dict[str, str]:
    return {'status': 'healthy'}


@v1.get('/messages', response_model=list[MessageOut])
async def list_messages() -> list[MessageOut]:
    return [to_message_out(message) for message in messages]


@v1.post('/messages', response_model=MessageOut)
async def create_message(payload: MessageIn) -> MessageOut:
    message = ChatMessage(
        id=uuid4(),
        sender=payload.sender,
        text=payload.text,
        created_at=datetime.now(UTC),
    )
    messages.append(message)
    message_out = to_message_out(message)
    await ws_manager.broadcast_json(
        {'type': 'message', 'data': message_out.model_dump(mode='json')}
    )
    return message_out


@v1.get('/ws/health')
async def websocket_health() -> dict[str, int]:
    return {'active_connections': ws_manager.active_count}


@v1.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    await websocket.send_json(
        {
            'type': 'system',
            'data': {
                'message': 'connected',
                'active_connections': ws_manager.active_count,
            },
        }
    )
    try:
        while True:
            incoming = await websocket.receive_json()
            if not isinstance(incoming, dict):
                continue
            if incoming.get('kind') == 'ping':
                continue
            await ws_manager.broadcast_json(
                {'type': 'event', 'data': incoming}
            )
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket)


app.include_router(v1)
