import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import websockets

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
        self.heartbeat_task: asyncio.Task | None = None
        self.relay_url: str | None = None
        self.stopping = False

    async def start(self) -> None:
        if not self.config.relay_url:
            raise ValueError('relay_url is required for relay mode')

        self.relay_url = self._normalize_relay_url(self.config.relay_url)
        self.stopping = False
        await self._connect()
        self.read_task = asyncio.create_task(self._read_loop())
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        self.stopping = True
        if self.read_task is not None:
            self.read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.read_task
            self.read_task = None

        if self.heartbeat_task is not None:
            self.heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.heartbeat_task
            self.heartbeat_task = None

        await self._reset_websocket()

    async def _connect(self) -> None:
        if not self.relay_url:
            raise ValueError('relay_url is required for relay mode')

        self.websocket = await websockets.connect(
            self.relay_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        )
        self.on_status(f'Connected to relay {self.relay_url}')

    async def send(self, text: str) -> None:
        if self.websocket is None:
            self.on_status('Not connected.')
            return

        payload = {
            'kind': 'message',
            'sender': self.config.username,
            'text': text,
        }
        try:
            await self.websocket.send(json.dumps(payload))
        except websockets.ConnectionClosed:
            self.on_status('Relay disconnected; reconnecting...')
            await self._reset_websocket()

    async def send_typing(self, active: bool) -> None:
        if self.websocket is None:
            return

        payload = {
            'kind': 'typing',
            'sender': self.config.username,
            'active': active,
        }
        try:
            await self.websocket.send(json.dumps(payload))
        except websockets.ConnectionClosed:
            await self._reset_websocket()

    async def _read_loop(self) -> None:
        while not self.stopping:
            if self.websocket is None:
                try:
                    await self._connect()
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    self.on_status(f'Relay connect failed: {exc}')
                    await asyncio.sleep(1.5)
                    continue

            try:
                assert self.websocket is not None
                async for raw in self.websocket:
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
            except websockets.ConnectionClosed:
                if not self.stopping:
                    self.on_status('Relay disconnected; reconnecting...')
            except Exception as exc:
                if not self.stopping:
                    self.on_status(f'Relay error: {exc}; reconnecting...')
            finally:
                await self._reset_websocket()

            if not self.stopping:
                await asyncio.sleep(1.5)

    async def _heartbeat_loop(self) -> None:
        while not self.stopping:
            await asyncio.sleep(5)
            if self.websocket is None:
                continue

            payload = {
                'kind': 'ping',
                'sender': 'ogham-chat',
                'is_system': True,
                'ts': datetime.now(UTC).isoformat(),
            }
            try:
                await self.websocket.send(json.dumps(payload))
            except websockets.ConnectionClosed:
                await self._reset_websocket()

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
        # REVIEW: not sure about 'get' here - gotta figure out safe defaults
        if isinstance(text, str) and text:
            message_data = {
                'id': data.get('id', uuid4()),
                'sender': str(sender),
                'text': text,
                'created_at': data.get('created_at', datetime.now(UTC)),
                'is_system': bool(data.get('is_system', False)),
            }
            self.on_message(ChatMessage.model_validate(message_data))

    async def _reset_websocket(self) -> None:
        if self.websocket is not None:
            with contextlib.suppress(Exception):
                await self.websocket.close()
            self.websocket = None

    def _normalize_relay_url(self, relay_url: str) -> str:
        parts = urlsplit(relay_url)
        match parts.scheme:
            case 'wss':
                return relay_url
            case 'https':  # replace https with wss, keep rest of URL
                return urlunsplit(('wss', *parts[1:]))
            case 'http' | 'ws':
                raise ValueError('Insecure relay URL scheme not allowed.')
            case _:
                raise ValueError(
                    'Unsupported relay URL scheme "{parts.scheme}"'
                )
