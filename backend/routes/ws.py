import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.realtime import RedisRealtimeCoordinator
from backend.store.base import MessageStoreProtocol
from backend.ws.manager import ConnectionManager


def create_ws_router(
    ws_manager: ConnectionManager,
    store: MessageStoreProtocol,
    realtime: RedisRealtimeCoordinator,
) -> APIRouter:
    """Create websocket routes for realtime chat transport events."""
    router = APIRouter()

    @router.websocket('/ws/{user_id}')
    async def websocket_endpoint(websocket: WebSocket, user_id: str) -> None:
        """Handle one websocket connection for a user.

        The endpoint processes three packet types:
        - message: store and forward direct messages.
        - typing: forward typing state to one recipient.
        - announce: broadcast arbitrary presence-like packets to others.
        """
        await ws_manager.connect(user_id, websocket)
        await realtime.register_local_presence(
            user_id,
            is_first_local_connection=(
                ws_manager.connection_count_for_user(user_id) == 1
            ),
        )

        await websocket.send_json(
            {
                'type': 'system',
                'data': {
                    'message': 'connected',
                    'user_id': user_id,
                    'active_users': ws_manager.active_user_count,
                    'active_connections': ws_manager.active_connection_count,
                },
            }
        )

        # Tell everyone (including the new user) who is online.
        await realtime.broadcast_presence_snapshot()

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    packet = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue

                packet_type = packet.get('type')

                if packet_type == 'message':
                    data = packet.get('data')
                    if isinstance(data, dict):
                        from backend.core.message import ChatMessage

                        try:
                            msg = ChatMessage.model_validate(data)
                        except ValidationError as exc:
                            await websocket.send_json(
                                {
                                    'type': 'error',
                                    'data': {
                                        'code': 'invalid_message',
                                        'message': str(exc.errors()[0]['msg']),
                                    },
                                }
                            )
                            continue

                        store.add(msg)
                        await ws_manager.send_to_user(msg.to, packet)
                        await realtime.publish_direct_message(msg.to, packet)

                elif packet_type == 'typing':
                    data = packet.get('data')
                    if isinstance(data, dict):
                        recipient = data.get('to')
                        if isinstance(recipient, str):
                            await ws_manager.send_to_user(recipient, packet)
                            await realtime.publish_typing(recipient, packet)

                elif packet_type == 'announce':
                    await ws_manager.broadcast_to_others(user_id, packet)

        except WebSocketDisconnect:
            pass
        finally:
            ws_manager.disconnect(user_id, websocket)
            await realtime.unregister_local_presence(
                user_id,
                lost_last_local_connection=(not ws_manager.has_user(user_id)),
            )
            await realtime.broadcast_presence_snapshot()

    return router
