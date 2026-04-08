import asyncio
import json
from typing import Callable

from backend.models import ChatConfig


class LocalChatBackend:
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
        self.server: asyncio.AbstractServer | None = None
        self.server_writer: asyncio.StreamWriter | None = None
        self.peer_writers: set[asyncio.StreamWriter] = set()
        self.tasks: set[asyncio.Task] = set()
        self.stopping = False

    async def start(self) -> None:
        if self.config.mode == 'host':
            self.server = await asyncio.start_server(
                self._handle_peer, host='127.0.0.1', port=self.config.port
            )
            self.on_status(f'Hosting on 127.0.0.1:{self.config.port}')

        reader, writer = await asyncio.open_connection(
            self.config.host, self.config.port
        )
        self.server_writer = writer
        self.on_status(f'Connected to {self.config.host}:{self.config.port}')
        self._track_task(asyncio.create_task(self._read_loop(reader, writer)))

    async def stop(self) -> None:
        self.stopping = True
        for task in list(self.tasks):
            task.cancel()
        self.tasks.clear()

        if self.server_writer is not None:
            self.server_writer.close()
            await self.server_writer.wait_closed()

        for writer in list(self.peer_writers):
            writer.close()
            await writer.wait_closed()
        self.peer_writers.clear()

        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()

    async def send(self, text: str) -> None:
        payload = (
            json.dumps(
                {
                    'type': 'message',
                    'name': self.config.username,
                    'text': text,
                }
            )
            + '\n'
        )

        if self.server_writer is None:
            self.on_status('Not connected.')
            return

        self.server_writer.write(payload.encode('utf-8'))
        await self.server_writer.drain()

    async def send_typing(self, active: bool) -> None:
        payload = (
            json.dumps(
                {
                    'type': 'typing',
                    'name': self.config.username,
                    'active': active,
                }
            )
            + '\n'
        )

        if self.server_writer is None:
            return

        self.server_writer.write(payload.encode('utf-8'))
        await self.server_writer.drain()

    async def _handle_peer(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.peer_writers.add(writer)
        self.on_status('Peer connected')
        self._track_task(asyncio.create_task(self._read_loop(reader, writer)))

    async def _read_loop(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break

                try:
                    packet = json.loads(line.decode('utf-8'))
                    packet_type = packet.get('type', 'message')
                    name = packet.get('name', 'unknown')
                except json.JSONDecodeError:
                    continue

                if packet_type == 'typing':
                    active = bool(packet.get('active', False))
<<<<<<< HEAD
                    if self.config.mode == 'host' and writer in self.peer_writers:
=======
                    if (
                        self.config.mode == 'host'
                        and writer in self.peer_writers
                    ):
>>>>>>> 088ad79 (feat: implement typing indicator functionality in chat application)
                        await self._broadcast(line)
                    else:
                        self.on_typing(name, active)
                    continue

                text = packet.get('text', '')

                if self.config.mode == 'host' and writer in self.peer_writers:
                    await self._broadcast(line)
                else:
                    self.on_message(name, text)
        except asyncio.CancelledError:
            return
        finally:
            if writer in self.peer_writers:
                self.peer_writers.remove(writer)
            writer.close()
            await writer.wait_closed()
            if not self.stopping:
                self.on_status('Peer disconnected')

    async def _broadcast(
        self, packet: bytes, exclude: asyncio.StreamWriter | None = None
    ) -> None:
        dead: list[asyncio.StreamWriter] = []
        for peer in self.peer_writers:
            if peer is exclude:
                continue
            try:
                peer.write(packet)
                await peer.drain()
            except ConnectionError:
                dead.append(peer)

        for peer in dead:
            self.peer_writers.discard(peer)

    def _track_task(self, task: asyncio.Task) -> None:
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
