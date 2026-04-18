from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

from backend.core.config import ChatConfig
from backend.core.message import ChatMessage


class RelayChatBackend:
    """Relay-backed chat transport for sending and receiving direct messages.

    This backend keeps a persistent WebSocket connection to the relay and
    forwards inbound events to UI callbacks.
    """

    def __init__(
        self,
        config: ChatConfig,
        on_message: Callable[[ChatMessage], None],
        on_status: Callable[[str], None],
        on_typing: Callable[[str, bool], None],
        on_user_list: Callable[[list[str]], None] | None = None,
    ) -> None:
        self.config = config
        self.on_message = on_message
        self.on_status = on_status
        self.on_typing = on_typing
        self.on_user_list = on_user_list

        self.websocket: websockets.ClientConnection | None = None
        self.read_task: asyncio.Task[None] | None = None
        self.relay_url: str | None = None
        self.stopping = False

    async def start(self) -> None:
        """Start the relay connection loop.

        Raises:
            ValueError: If relay mode is selected without a relay URL.
        """
        if not self.config.relay_url:
            raise ValueError('relay_url is required for relay mode')

        self.relay_url = self._normalize_relay_url(
            self.config.relay_url,
            self.config.username,
        )
        self.stopping = False
        self.on_status(f'Connecting to relay {self.relay_url}...')

        if self.read_task is None:
            self.read_task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        """Stop background relay reads and close the active websocket."""
        self.stopping = True

        if self.read_task is not None:
            self.read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.read_task
            self.read_task = None

        await self._close_current_websocket()

    async def send(
        self, content: str, to: str | None = None, metadata: dict | None = None
    ) -> None:
        """Send a chat message to one recipient through the relay.

        Args:
            content: Message text to send.
            to: Explicit recipient user id. Falls back to configured peer.
            metadata: Optional metadata dict attached to the message.
        """
        websocket = self.websocket
        if websocket is None:
            self.on_status('Not connected; waiting for relay reconnect...')
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

        payload = {
            'type': 'message',
            'data': message.model_dump(mode='json'),
        }

        try:
            await websocket.send(json.dumps(payload))
            self.on_message(message)
        except ConnectionClosed:
            self.on_status('Relay disconnected; reconnecting...')
            self.websocket = None

    async def send_typing(self, active: bool, to: str | None = None) -> None:
        """Send typing activity state for a recipient.

        Args:
            active: Whether typing is currently active.
            to: Explicit recipient user id. Falls back to configured peer.
        """
        websocket = self.websocket
        if websocket is None:
            return

        recipient = (to or self.config.peer or '').strip()
        if not recipient:
            return

        payload = {
            'type': 'typing',
            'data': {
                'sender': self.config.username,
                'to': recipient,
                'active': active,
            },
        }

        try:
            await websocket.send(json.dumps(payload))
        except ConnectionClosed:
            self.websocket = None

    async def _read_loop(self) -> None:
        """Maintain relay connectivity and dispatch inbound packets."""
        if not self.relay_url:
            return

        try:
            async for websocket in websockets.connect(
                self.relay_url,
                ping_interval=10,
                ping_timeout=10,
                close_timeout=5,
                open_timeout=10,
                process_exception=self._process_connect_exception,
            ):
                if self.stopping:
                    await websocket.close()
                    return

                self.websocket = websocket
                self.on_status(f'Connected to relay {self.relay_url}')

                try:
                    async for raw in websocket:
                        try:
                            packet = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        try:
                            self._handle_packet(packet)
                        except Exception as exc:
                            self.on_status(f'Ignored malformed packet: {exc}')
                except asyncio.CancelledError:
                    return
                except ConnectionClosed:
                    if not self.stopping:
                        self.on_status('Relay disconnected; reconnecting...')
                finally:
                    if self.websocket is websocket:
                        self.websocket = None
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if not self.stopping:
                self.on_status(f'Relay fatal error: {exc}')

    def _process_connect_exception(self, exc: Exception) -> Exception | None:
        """Classify handshake exceptions as retryable or fatal.

        Returns:
            None for transient failures that should be retried, otherwise the
            original exception to stop reconnect attempts.
        """
        # Retry common transient/proxy-origin errors instead of treating them as fatal.
        if isinstance(exc, InvalidStatus):
            status_code = getattr(exc, 'status_code', None)
            if status_code is None:
                response = getattr(exc, 'response', None)
                status_code = getattr(response, 'status_code', None)

            if status_code in {
                429,
                500,
                502,
                503,
                504,
                520,
                521,
                522,
                523,
                524,
                525,
                526,
            }:
                self.on_status(
                    f'Relay handshake failed (HTTP {status_code}); retrying...'
                )
                return None

        return exc

    def _handle_packet(self, packet: dict) -> None:
        """Dispatch one decoded relay packet to callbacks.

        Supported packet types are system, user_list, typing, and message.
        """
        packet_type = packet.get('type')

        if packet_type == 'system':
            data = packet.get('data', {})
            if isinstance(data, dict):
                message = data.get('message')
                if isinstance(message, str) and message:
                    self.on_status(f'Relay: {message}')
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
            recipient = data.get('to')
            active = bool(data.get('active', False))

            if (
                isinstance(sender, str)
                and isinstance(recipient, str)
                and recipient == self.config.username
                and sender != self.config.username
            ):
                self.on_typing(sender, active)
            return

        if packet_type != 'message':
            return

        data = packet.get('data')
        if not isinstance(data, dict):
            return

        message = ChatMessage.model_validate(data)

        # Ignore our own echoes if the server ever sends them back.
        if message.sender == self.config.username:
            return

        # Ignore messages not addressed to us.
        if message.to != self.config.username:
            return

        self.on_message(message)

    async def _close_current_websocket(self) -> None:
        """Close and clear the active websocket reference if present."""
        websocket = self.websocket
        self.websocket = None
        if websocket is not None:
            with contextlib.suppress(ConnectionClosed, RuntimeError):
                await websocket.close()

    def _normalize_relay_url(self, relay_url: str, username: str) -> str:
        """Normalize relay URL scheme and path for per-user websocket routing.

        Args:
            relay_url: User-provided relay URL.
            username: Local user id appended when URL ends in /ws.

        Raises:
            ValueError: If the scheme is insecure or unsupported.
        """
        parts = urlsplit(relay_url)

        match parts.scheme:
            case 'wss':
                base = relay_url
            case 'https':
                base = urlunsplit(('wss', *parts[1:]))
            case 'http' | 'ws':
                raise ValueError('Insecure relay URL scheme not allowed.')
            case _:
                raise ValueError(
                    f'Unsupported relay URL scheme "{parts.scheme}"'
                )

        # Ensure the websocket path is user-specific: /ws/{user_id}
        normalized = base.rstrip('/')
        if normalized.endswith('/ws'):
            return f'{normalized}/{username}'

        return normalized
