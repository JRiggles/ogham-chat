import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.store.base import MessageStoreProtocol
from backend.ws.manager import ConnectionManager


def create_ws_router(
    ws_manager: ConnectionManager,
    store: MessageStoreProtocol,
) -> APIRouter:
    router = APIRouter()

    @router.websocket('/ws/{user_id}')
    async def websocket_endpoint(websocket: WebSocket, user_id: str) -> None:
        await ws_manager.connect(user_id, websocket)

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
        await ws_manager.broadcast_user_list()

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    packet = json.loads(raw)
                except json.JSONDecodeError, TypeError:
                    continue

                packet_type = packet.get('type')

                if packet_type == 'message':
                    data = packet.get('data')
                    if isinstance(data, dict):
                        from backend.core.message import ChatMessage

                        msg = ChatMessage.model_validate(data)
                        store.add(msg)
                        await ws_manager.send_to_user(msg.to, packet)

                elif packet_type == 'typing':
                    data = packet.get('data')
                    if isinstance(data, dict):
                        recipient = data.get('to')
                        if isinstance(recipient, str):
                            await ws_manager.send_to_user(recipient, packet)

                elif packet_type == 'announce':
                    await ws_manager.broadcast_to_others(user_id, packet)

        except WebSocketDisconnect:
            pass
        finally:
            ws_manager.disconnect(user_id, websocket)
            await ws_manager.broadcast_user_list()

    return router
