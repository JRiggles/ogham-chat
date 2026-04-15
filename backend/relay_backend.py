import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import websockets
from websockets.exceptions import ConnectionClosed

from backend.models import ChatConfig
from backend.types import ChatMessage


class RelayChatBackend:
    def __init__(
        self,
        config: ChatConfig,
        on_message: Callable[[ChatMessage], None],
        on_status: Callable[[str], None],
        on_typing: Callable[[str, bool], None],
    ) -> None:
        self.config = config
        self.on_message = on_message
        self.on_status = on_status
        self.on_typing = on_typing
        self.websocket = None
        self.read_task: asyncio.Task | None = None
        self.relay_url: str | None = None
        self.stopping = False

    async def start(self) -> None:
        if not self.config.relay_url:
            raise ValueError('relay_url is required for relay mode')

        self.relay_url = self._normalize_relay_url(self.config.relay_url)
        self.stopping = False
        self.on_status(f'Connecting to relay {self.relay_url}...')
        if self.read_task is None:
            self.read_task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        self.stopping = True
        if self.read_task is not None:
            self.read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.read_task
            self.read_task = None

        await self._close_current_websocket()

    async def send(self, text: str) -> None:
        websocket = self.websocket
        if websocket is None:
            self.on_status('Not connected; waiting for relay reconnect...')
            return

        payload = {
            'kind': 'message',
            'sender': self.config.username,
            'text': text,
        }
        try:
            await websocket.send(json.dumps(payload))
        except ConnectionClosed:
            self.on_status('Relay disconnected; reconnecting...')
            self.websocket = None

    async def send_typing(self, active: bool) -> None:
        websocket = self.websocket
        if websocket is None:
            return

        payload = {
            'kind': 'typing',
            'sender': self.config.username,
            'active': active,
        }
        try:
            await websocket.send(json.dumps(payload))
        except ConnectionClosed:
            self.websocket = None

    async def _read_loop(self) -> None:
        if not self.relay_url:
            return

        try:
            async for websocket in websockets.connect(
                self.relay_url,
                ping_interval=10,
                ping_timeout=10,
                close_timeout=5,
                open_timeout=10,
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

    def _handle_packet(self, packet: dict) -> None:
        packet_type = packet.get('type')
        if packet_type == 'system':
            data = packet.get('data', {})
            message = data.get('message')
            if isinstance(message, str) and message:
                self.on_status(f'Relay: {message}')
            return

        data = packet.get('data', packet)
        if not isinstance(data, dict):
            return

        kind = data.get('kind')
        sender = data.get('sender') or data.get('name') or 'unknown'

        if kind == 'typing':
            self.on_typing(str(sender), bool(data.get('active', False)))
            return

        text = data.get('text')
        if isinstance(text, str) and text:
            message_data = {
                'id': data.get('id', uuid4()),
                'sender': str(sender),
                'text': text,
                'created_at': data.get('created_at', datetime.now(UTC)),
                'is_system': bool(data.get('is_system', False)),
            }
            self.on_message(ChatMessage.model_validate(message_data))

    async def _close_current_websocket(self) -> None:
        websocket = self.websocket
        self.websocket = None
        if websocket is not None:
            with contextlib.suppress(ConnectionClosed, RuntimeError):
                await websocket.close()

    def _normalize_relay_url(self, relay_url: str) -> str:
        parts = urlsplit(relay_url)
        match parts.scheme:
            case 'wss':
                return relay_url
            case 'https':
                return urlunsplit(('wss', *parts[1:]))
            case 'http' | 'ws':
                raise ValueError('Insecure relay URL scheme not allowed.')
            case _:
                raise ValueError(
                    f'Unsupported relay URL scheme "{parts.scheme}"'
                )
