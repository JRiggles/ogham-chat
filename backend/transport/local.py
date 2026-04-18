from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Callable
from uuid import uuid4

import websockets
from websockets.exceptions import ConnectionClosed

from backend.core.config import ChatConfig
from backend.core.message import ChatMessage


class LocalChatBackend:
    """WebSocket-based local backend.

    In **host** mode a lightweight ``websockets`` server is started on the
    configured port.  In **join** mode, a client connects to that server.
    Messages and typing indicators are forwarded over the link so both
    peers see each other's activity.
    """

    def __init__(
        self,
        config: ChatConfig,
        on_message: Callable[[ChatMessage], None],
        on_status: Callable[[str], None],
        on_typing: Callable[[str, bool], None],
        on_user_list: Callable[[list[str]], None] | None = None,
    ) -> None:
        """Initialize callbacks and websocket state for host/join modes."""
        self.config = config
        self.on_message = on_message
        self.on_status = on_status
        self.on_typing = on_typing
        self.on_user_list = on_user_list

        self.running = False
        self._peers: set[websockets.ServerConnection] = set()
        self._peer_names: dict[websockets.ServerConnection, str] = {}
        self._ws: websockets.ClientConnection | None = None
        self._server: websockets.Server | None = None
        self._tasks: list[asyncio.Task[None]] = []

    # ── lifecycle ──────────────────────────────────────────────

    async def start(self) -> None:
        """Start local chat transport in host or join mode."""
        self.running = True

        if self.config.mode == 'host':
            self._server = await websockets.serve(
                self._host_handler,
                self.config.host,
                self.config.port,
            )
            self.on_status(
                f'Hosting on {self.config.host}:{self.config.port} — waiting for peer…'
            )
        else:
            self._tasks.append(asyncio.create_task(self._join_loop()))

    async def stop(self) -> None:
        """Stop local transport tasks and close server/client sockets."""
        self.running = False

        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        await self._close_ws()

    # ── sending ────────────────────────────────────────────────

    async def send(self, content: str, to: str | None = None, metadata: dict | None = None) -> None:
        """Send one chat message to connected peers or host server."""
        if not self.running:
            self.on_status('Local backend is not running')
            return

        recipient = (to or self.config.peer or '').strip()
        if not recipient:
            self.on_status('No recipient selected')
            return

        message = ChatMessage(
            message_id=uuid4(),
            sender=self.config.username,
            to=recipient,
            content=content,
            created_at=datetime.now(UTC),
            is_system=False,
            metadata=metadata,
        )

        payload = json.dumps(
            {
                'type': 'message',
                'data': message.model_dump(mode='json'),
            }
        )

        await self._broadcast(payload)

        # Show the message in our own UI as well.
        self.on_message(message)
        self.on_status('Sent')

    async def send_typing(self, active: bool, to: str | None = None) -> None:
        """Broadcast typing activity changes to the current recipient."""
        if not self.running:
            return

        recipient = (to or self.config.peer or '').strip()
        if not recipient:
            return

        payload = json.dumps(
            {
                'type': 'typing',
                'data': {
                    'sender': self.config.username,
                    'to': recipient,
                    'active': active,
                },
            }
        )

        await self._broadcast(payload)

    # ── host: server handling ──────────────────────────────────

    async def _host_handler(
        self, websocket: websockets.ServerConnection
    ) -> None:
        """Handle one inbound peer connection when running in host mode."""
        self._peers.add(websocket)
        self.on_status('Peer connected')

        # Send our own announce so the joiner learns our username.
        await websocket.send(self._announce_payload())

        try:
            async for raw in websocket:
                packet = self._parse_packet(raw)
                if packet and packet.get('type') == 'announce':
                    data = packet.get('data', {})
                    name = (
                        data.get('username')
                        if isinstance(data, dict)
                        else None
                    )
                    if isinstance(name, str):
                        self._peer_names[websocket] = name
                        self._broadcast_user_list()
                self._handle_packet(raw)
                # Forward to other connected peers (not back to sender).
                for peer in list(self._peers):
                    if peer is not websocket:
                        with contextlib.suppress(ConnectionClosed):
                            await peer.send(raw)
        except ConnectionClosed:
            pass
        finally:
            self._peers.discard(websocket)
            self._peer_names.pop(websocket, None)
            self._broadcast_user_list()
            if self.running:
                self.on_status('Peer disconnected')

    # ── join: client loop ──────────────────────────────────────

    async def _join_loop(self) -> None:
        """Maintain a reconnecting websocket client loop in join mode."""
        url = f'ws://{self.config.host}:{self.config.port}'
        self.on_status(f'Connecting to {self.config.host}:{self.config.port}…')

        try:
            async for websocket in websockets.connect(
                url,
                ping_interval=10,
                ping_timeout=10,
                close_timeout=5,
                open_timeout=10,
            ):
                if not self.running:
                    await websocket.close()
                    return

                self._ws = websocket
                self.on_status(
                    f'Connected to {self.config.host}:{self.config.port}'
                )

                # Announce ourselves so the host learns our username.
                await websocket.send(self._announce_payload())

                try:
                    async for raw in websocket:
                        self._handle_packet(raw)
                except asyncio.CancelledError:
                    return
                except ConnectionClosed:
                    if self.running:
                        self.on_status('Disconnected; reconnecting…')
                finally:
                    if self._ws is websocket:
                        self._ws = None
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if self.running:
                self.on_status(f'Connection error: {exc}')

    # ── shared helpers ─────────────────────────────────────────

    async def _broadcast(self, payload: str) -> None:
        """Send *payload* to all connected sockets (peers or server)."""
        # Host mode: push to every connected peer.
        for peer in list(self._peers):
            with contextlib.suppress(ConnectionClosed):
                await peer.send(payload)

        # Join mode: push to the server.
        ws = self._ws
        if ws is not None:
            try:
                await ws.send(payload)
            except ConnectionClosed:
                self._ws = None
                self.on_status('Disconnected; reconnecting…')

    def _handle_packet(self, raw: str | bytes) -> None:
        """Decode and dispatch inbound local transport packets."""
        try:
            packet = json.loads(raw)
        except json.JSONDecodeError:
            return

        packet_type = packet.get('type')

        if packet_type == 'announce':
            # Handled separately in _host_handler; join side uses user_list.
            return

        if packet_type == 'user_list':
            data = packet.get('data')
            if isinstance(data, dict):
                users = data.get('users')
                if isinstance(users, list) and self.on_user_list:
                    self.on_user_list([u for u in users if isinstance(u, str)])
            return

        if packet_type == 'typing':
            data = packet.get('data')
            if not isinstance(data, dict):
                return
            sender = data.get('sender')
            active = bool(data.get('active', False))
            if isinstance(sender, str) and sender != self.config.username:
                self.on_typing(sender, active)
            return

        if packet_type == 'message':
            data = packet.get('data')
            if not isinstance(data, dict):
                return
            message = ChatMessage.model_validate(data)
            if message.sender == self.config.username:
                return
            self.on_message(message)

    def _announce_payload(self) -> str:
        """Build an announce packet containing the local username."""
        return json.dumps(
            {'type': 'announce', 'data': {'username': self.config.username}}
        )

    def _parse_packet(self, raw: str | bytes) -> dict | None:
        """Parse raw websocket payload into a packet dict if valid JSON."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _broadcast_user_list(self) -> None:
        """Push the current user list to all peers and our own UI."""
        users = [self.config.username] + list(self._peer_names.values())
        if self.on_user_list:
            self.on_user_list(users)
        # Send to each peer so they update their contact lists too.
        payload = json.dumps({'type': 'user_list', 'data': {'users': users}})
        loop = asyncio.get_running_loop()
        for peer in list(self._peers):
            loop.create_task(self._send_safe(peer, payload))

    @staticmethod
    async def _send_safe(
        ws: websockets.ServerConnection, payload: str
    ) -> None:
        """Send payload to one socket while suppressing disconnect errors."""
        with contextlib.suppress(ConnectionClosed):
            await ws.send(payload)

    async def _close_ws(self) -> None:
        """Close and clear the active join-mode websocket if present."""
        ws = self._ws
        self._ws = None
        if ws is not None:
            with contextlib.suppress(ConnectionClosed, RuntimeError):
                await ws.close()
