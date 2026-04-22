import contextlib
from collections import defaultdict
from typing import DefaultDict

from fastapi import WebSocket


class ConnectionManager:
    """Track active websocket connections keyed by user id."""

    def __init__(self) -> None:
        """Initialize an empty user-to-connections mapping."""
        self._connections: DefaultDict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        """Accept and register a websocket for a user."""
        await websocket.accept()
        self._connections[user_id].append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        """Remove a websocket from tracking and prune empty users."""
        conns = self._connections.get(user_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns and user_id in self._connections:
            del self._connections[user_id]

    async def broadcast_user_list(self) -> None:
        """Send the current online user list to every connected client."""
        payload = {
            'type': 'user_list',
            'data': {'users': self.connected_user_ids},
        }
        for conns in list(self._connections.values()):
            for websocket in list(conns):
                with contextlib.suppress(Exception):
                    await websocket.send_json(payload)

    async def send_to_user(self, user_id: str, payload: dict) -> None:
        """Send a payload to all active sockets currently attached to a user."""
        conns = list(self._connections.get(user_id, []))
        stale: list[WebSocket] = []

        for websocket in conns:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)

        for websocket in stale:
            self.disconnect(user_id, websocket)

    async def broadcast_to_others(self, sender_id: str, payload: dict) -> None:
        """Send *payload* to every connected user except *sender_id*."""
        for user_id, conns in list(self._connections.items()):
            if user_id == sender_id:
                continue
            stale: list[WebSocket] = []
            for websocket in list(conns):
                try:
                    await websocket.send_json(payload)
                except Exception:
                    stale.append(websocket)
            for websocket in stale:
                self.disconnect(user_id, websocket)

    @property
    def connected_user_ids(self) -> list[str]:
        """Return currently connected user ids."""
        return list(self._connections.keys())

    @property
    def active_user_count(self) -> int:
        """Return how many distinct users are connected."""
        return len(self._connections)

    @property
    def active_connection_count(self) -> int:
        """Return the total number of active websocket connections."""
        return sum(len(v) for v in self._connections.values())
