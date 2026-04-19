from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.core.message import ChatMessage
from backend.store.base import MessageStoreProtocol
from backend.ws.manager import ConnectionManager


def create_messages_router(
    ws_manager: ConnectionManager,
    store: MessageStoreProtocol,
) -> APIRouter:
    """Create HTTP routes for storing and querying chat message history."""
    router = APIRouter()

    @router.post('/messages', deprecated=True)
    async def create_message(message: ChatMessage) -> JSONResponse:
        """Reserved for future use (e.g. HTTP-only clients, integrations)."""
        return JSONResponse(
            status_code=501,
            content={'detail': 'This endpoint is reserved for future use.'},
        )

    @router.get('/messages/sync', response_model=list[ChatMessage])
    async def sync_messages(
        user_id: str,
        after: datetime | None = Query(default=None),
    ) -> list[ChatMessage]:
        """Return messages addressed to a user, optionally after a timestamp."""
        return store.get_for_user_after(user_id=user_id, after=after)

    @router.get('/messages/conversation', response_model=list[ChatMessage])
    async def get_conversation(
        user_id: str,
        peer_id: str,
        after: datetime | None = Query(default=None),
    ) -> list[ChatMessage]:
        """Return the ordered conversation between two users."""
        return store.get_conversation(
            user_id=user_id,
            peer_id=peer_id,
            after=after,
        )

    return router
