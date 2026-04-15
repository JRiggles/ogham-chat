import asyncio
import contextlib
import json
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import websockets

from backend.models import ChatConfig


class RelayChatBackend:
    def __init__(
        self,
        config: ChatConfig,
        on_message: Callable[[str, str], None],
        on_status: Callable[[str], None],
        on_typing: Callable[[str, bool], None],
    ) -> None:
        self.config = config
        self.on_message = on_message
        self.on_status = on_status
        self.on_typing = on_typing
        self.websocket = None
        self.read_task: asyncio.Task | None = None
        self.stopping = False

    async def start(self) -> None:
        if not self.config.relay_url:
            raise ValueError('relay_url is required for relay mode')

        relay_url = self._normalize_relay_url(self.config.relay_url)
        self.websocket = await websockets.connect(relay_url)
        self.on_status(f'Connected to relay {relay_url}')
        self.read_task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        self.stopping = True
        if self.read_task is not None:
            self.read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.read_task

        if self.websocket is not None:
            await self.websocket.close()
            self.websocket = None

    async def send(self, text: str) -> None:
        if self.websocket is None:
            self.on_status('Not connected.')
            return

        payload = {
            'kind': 'message',
            'sender': self.config.username,
            'text': text,
        }
        await self.websocket.send(json.dumps(payload))

    async def send_typing(self, active: bool) -> None:
        if self.websocket is None:
            return

        payload = {
            'kind': 'typing',
            'sender': self.config.username,
            'active': active,
        }
        await self.websocket.send(json.dumps(payload))

    async def _read_loop(self) -> None:
        try:
            assert self.websocket is not None
            async for raw in self.websocket:
                try:
                    packet = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                self._handle_packet(packet)
        except asyncio.CancelledError:
            return
        except websockets.ConnectionClosed:
            if not self.stopping:
                self.on_status('Relay disconnected')

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
            self.on_message(str(sender), text)

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
