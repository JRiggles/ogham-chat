from datetime import datetime

from fastapi import APIRouter, Query

from backend.core.message import ChatMessage
from backend.store.base import MessageStoreProtocol
from backend.ws.manager import ConnectionManager


def create_messages_router(
    ws_manager: ConnectionManager,
    store: MessageStoreProtocol,
) -> APIRouter:
    router = APIRouter()

    @router.post('/messages', response_model=ChatMessage)
    async def create_message(message: ChatMessage) -> ChatMessage:
        store.add(message)

        await ws_manager.send_to_user(
            message.to,
            {
                'type': 'message',
                'data': message.model_dump(mode='json'),
            },
        )

        return message

    @router.get('/messages/sync', response_model=list[ChatMessage])
    async def sync_messages(
        user_id: str,
        after: datetime | None = Query(default=None),
    ) -> list[ChatMessage]:
        return store.get_for_user_after(user_id=user_id, after=after)

    @router.get('/messages/conversation', response_model=list[ChatMessage])
    async def get_conversation(
        user_id: str,
        peer_id: str,
        after: datetime | None = Query(default=None),
    ) -> list[ChatMessage]:
        return store.get_conversation(
            user_id=user_id,
            peer_id=peer_id,
            after=after,
        )

    return router
