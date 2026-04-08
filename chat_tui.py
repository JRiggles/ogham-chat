#!/usr/bin/env python3
import argparse
import asyncio
import json
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, cast

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Footer, Header, RichLog, Static, TextArea


@dataclass
class ChatConfig:
    mode: str
    username: str
    host: str
    port: int


@dataclass
class ChatMessage:
    username: str
    text: str
    timestamp: str
    is_system: bool = False


@dataclass
class ChatComposerSubmit(Message):
    text: str

    def __post_init__(self) -> None:
        Message.__post_init__(self)


class EnterToSubmitMixin:
    async def on_key(self, event: events.Key) -> None:
        # Let Shift+Enter (and any non-Enter key) fall through to TextArea.
        if event.key != 'enter':
            return

        composer = cast(TextArea, self)
        event.prevent_default()
        event.stop()
        composer.post_message(ChatComposerSubmit(composer.text))


class ChatMessageRenderer:
    def __init__(
        self,
        self_style: str = 'green',
        peer_style: str = 'blue',
    ) -> None:
        self.self_style = self_style
        self.peer_style = peer_style

    def render(
        self, message: ChatMessage, width: int, self_username: str
    ) -> list[Text]:
        if message.is_system:
            return self._render_system_message(message, width)

        is_self = message.username == self_username
        line_style = self.self_style if is_self else self.peer_style
        header_style = f'bold dim {line_style}'
        name_style = f'bold dim {line_style}'
        body_width = max(width, 1)

        rendered_lines: list[Text] = []

        header = f'{message.username} - {message.timestamp}'
        rendered_header = Text(header, style=header_style)
        name_start = rendered_header.plain.find(message.username)
        if name_start != -1:
            rendered_header.stylize(
                name_style,
                name_start,
                name_start + len(message.username),
            )
        rendered_lines.append(rendered_header)

        wrapped = textwrap.wrap(
            message.text,
            width=body_width,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        ) or ['']

        for chunk in wrapped:
            line = chunk
            rendered = Text(line, style=line_style)
            rendered_lines.append(rendered)

        rendered_lines.append(Text(''))

        return rendered_lines

    def _render_system_message(
        self, message: ChatMessage, width: int
    ) -> list[Text]:
        system_width = max(width, 1)
        wrapped_system = textwrap.wrap(
            message.text,
            width=system_width,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        ) or ['']
        rendered_system = [Text(line, style='dim') for line in wrapped_system]
        rendered_system.append(Text(''))  # add spacing after system messages
        return rendered_system


class ChatComposer(EnterToSubmitMixin, TextArea):
    pass


class ChatBackend:
    def __init__(
        self,
        config: ChatConfig,
        on_message: Callable[[str, str], None],
        on_status: Callable[[str], None],
    ) -> None:
        self.config = config
        self.on_message = on_message
        self.on_status = on_status
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
            json.dumps({'name': self.config.username, 'text': text}) + '\n'
        )

        # Always send via the server connection for consistency between host/client modes.
        if self.server_writer is None:
            self.on_status('Not connected.')
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
                    name = packet.get('name', 'unknown')
                    text = packet.get('text', '')
                except json.JSONDecodeError:
                    continue

                if self.config.mode == 'host' and writer in self.peer_writers:
                    # In host mode, peer messages are relayed to all connected peers,
                    # including the sender, so each terminal gets exactly one echo.
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


class ChatApp(App[None]):
    ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    TITLE = 'Ogham Chat'
    SUB_TITLE = 'Local Terminal Relay'

    CSS = """
    Screen {
        layout: vertical;
    }

    #chat {
        height: 1fr;
        overflow-x: hidden;
        overflow-y: auto;
        scrollbar-gutter: stable;
        border: round $accent;
        margin: 0 1;
        padding: 1 2 1 2;
    }

    #composer {
        height: 6;
        border: round $accent;
        margin: 0 1;
        padding: 1 2 1 2;
    }

    #status {
        height: 1;
        margin: 0 1;
    }
    """

    BINDINGS = [
        ('ctrl+c', 'quit', 'Quit'),
    ]

    def __init__(self, config: ChatConfig) -> None:
        super().__init__()
        self.config = config
        self.shutting_down = False
        self.messages: list[ChatMessage] = []
        self.renderer = ChatMessageRenderer()
        self.backend = ChatBackend(
            config, self._on_network_message, self._set_status
        )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Vertical(
            RichLog(id='chat', highlight=False, auto_scroll=True, wrap=True),
            ChatComposer('', id='composer'),
            Static('', id='status'),
        )
        yield Footer()

    async def on_mount(self) -> None:
        await self.backend.start()
        chat = self.query_one('#chat', RichLog)
        composer = self.query_one('#composer', TextArea)
        composer.focus()
        theme = self.get_theme(self.theme)
        if theme is None:
            self.renderer.self_style = 'green'
            self.renderer.peer_style = 'blue'
        else:
            self.renderer.self_style = str(theme.primary)
            self.renderer.peer_style = str(theme.success)
        self.title = f'Ogham Chat ᚛ᚑᚌᚆᚐᚋ᚜ Welcome {self.config.username}'
        if self.config.mode == 'host':
            self.sub_title = f'Hosting on 127.0.0.1:{self.config.port}'
        else:
            self.sub_title = (
                f'Connected to {self.config.host}:{self.config.port}'
            )
        chat.border_title = 'Chat Log'
        composer.border_title = (
            'Write a message (Enter: send | Shift+Enter: newline)'
        )
        self._set_status('Ready')

    async def on_unmount(self) -> None:
        self.shutting_down = True
        await self.backend.stop()

    def on_resize(self, event: events.Resize) -> None:
        del event
        self._rerender_messages()

    async def on_chat_composer_submit(
        self, message: ChatComposerSubmit
    ) -> None:
        composer = self.query_one('#composer', ChatComposer)
        text = self._sanitize_text(message.text).strip()
        composer.clear()
        if not text:
            return

        await self.backend.send(text)

    def _on_network_message(self, username: str, text: str) -> None:
        if self.shutting_down:
            return

        cleaned = self._sanitize_text(text)
        self.messages.append(
            ChatMessage(
                username=username,
                text=cleaned,
                timestamp=datetime.now().strftime('%H:%M:%S'),
            )
        )
        self._rerender_messages()

    def _set_status(self, text: str) -> None:
        if self.shutting_down:
            return

        try:
            status = self.query_one('#status', Static)
        except NoMatches:
            return

        status.update(f'{text} | Ctrl+C to quit')

    def _write_system_message(self, text: str) -> None:
        self.messages.append(
            ChatMessage(
                username='system',
                text=self._sanitize_text(text),
                timestamp=datetime.now().strftime('%H:%M:%S'),
                is_system=True,
            )
        )
        self._rerender_messages()

    def _sanitize_text(self, text: str) -> str:
        text = self.ANSI_ESCAPE_RE.sub('', text)
        return ''.join(
            ch for ch in text if ch == '\t' or ch == ' ' or ch.isprintable()
        )

    def _rerender_messages(self) -> None:
        if self.shutting_down:
            return

        try:
            log = self.query_one('#chat', RichLog)
        except NoMatches:
            return

        width = max(log.size.width, 1)
        log.clear()

        for message in self.messages:
            rendered_lines = self.renderer.render(
                message, width=width, self_username=self.config.username
            )
            for line in rendered_lines:
                log.write(line)


def parse_args() -> ChatConfig:
    parser = argparse.ArgumentParser(
        description='Minimal local terminal chat with Textual'
    )
    subparsers = parser.add_subparsers(dest='mode', required=True)

    host_parser = subparsers.add_parser(
        'host', help='Run host and join from this terminal'
    )
    host_parser.add_argument('--port', type=int, default=9000)
    host_parser.add_argument('--name', default='host')

    join_parser = subparsers.add_parser(
        'join', help='Join an existing local host'
    )
    join_parser.add_argument('--host', default='127.0.0.1')
    join_parser.add_argument('--port', type=int, default=9000)
    join_parser.add_argument('--name', default='guest')

    args = parser.parse_args()

    if args.mode == 'host':
        return ChatConfig(
            mode='host', username=args.name, host='127.0.0.1', port=args.port
        )

    return ChatConfig(
        mode='join', username=args.name, host=args.host, port=args.port
    )


def main() -> None:
    config = parse_args()
    ChatApp(config).run()


if __name__ == '__main__':
    main()
