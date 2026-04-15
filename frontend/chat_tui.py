#!/usr/bin/env python3
import argparse
import re
from datetime import UTC, datetime
from uuid import uuid4

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Static, TextArea

from backend import ChatConfig, LocalChatBackend, RelayChatBackend
from backend.types import ChatMessage
from components.chat_log import ChatLog
from components.composer import (
    ChatComposer,
    ChatComposerSubmit,
    ChatComposerTyping,
)
from frontend.assets.style.theme import NOSTALGOS_12


class ChatApp(App[None]):
    ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    TITLE = 'Ogham Chat'
    SUB_TITLE = 'Local Terminal Relay'  # TODO: dynamic status? better sub?
    CSS_PATH = 'assets/style/chat.tcss'

    BINDINGS = [
        ('ctrl+c', 'quit', 'Quit'),
    ]

    def __init__(self, config: ChatConfig) -> None:
        super().__init__()
        self.config = config
        self.shutting_down = False
        self.active_peer: str | None = None
        backend_cls = (
            RelayChatBackend if config.mode == 'relay' else LocalChatBackend
        )
        self.backend = backend_cls(
            config=config,
            on_message=self._on_network_message,
            on_status=self._set_status,
            on_typing=self._on_network_typing,
        )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Vertical(
            ChatLog(self_username=self.config.username, id='chat'),
            ChatComposer('', id='composer'),
            Static('', id='status'),
        )
        yield Footer()

    async def on_mount(self) -> None:
        self.register_theme(NOSTALGOS_12)
        self.theme = 'nostalgos-12'
        await self.backend.start()
        chat = self.query_one('#chat', ChatLog)
        composer = self.query_one('#composer', TextArea)
        composer.focus()
        theme = self.get_theme(self.theme)
        if theme is None:
            chat.set_message_styles('green', 'blue')
        else:
            chat.set_message_styles(str(theme.primary), str(theme.success))
        self.title = f'Ogham Chat ᚛ᚑᚌᚆᚐᚋ᚜ Welcome {self.config.username}'
        if self.config.mode == 'host':
            self.sub_title = f'Hosting on 127.0.0.1:{self.config.port}'
        elif self.config.mode == 'relay':
            self.sub_title = f'Connected to relay {self.config.relay_url}'
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
        self.query_one('#chat', ChatLog).rerender()

    async def on_chat_composer_submit(
        self, message: ChatComposerSubmit
    ) -> None:
        composer = self.query_one('#composer', ChatComposer)
        text = self._sanitize_text(message.text).strip()
        composer.clear()
        if not text:
            return

        await self.backend.send(text)
        await self.backend.send_typing(False)

    async def on_chat_composer_typing(
        self, message: ChatComposerTyping
    ) -> None:
        await self.backend.send_typing(message.active)

    def _on_network_message(self, message: ChatMessage) -> None:
        if self.shutting_down:
            return

        self._set_active_peer(message.sender)
        message.text = self._sanitize_text(message.text)
        chat = self.query_one('#chat', ChatLog)
        chat.set_peer_typing(message.sender, False)
        chat.append_message(message)

    def _on_network_typing(self, username: str, active: bool) -> None:
        if self.shutting_down:
            return

        self._set_active_peer(username)
        self.query_one('#chat', ChatLog).set_peer_typing(username, active)

    def _set_active_peer(self, username: str) -> None:
        if not username or username == self.config.username:
            return

        if self.active_peer == username:
            return

        self.active_peer = username
        self.query_one(
            '#chat', ChatLog
        ).border_title = f'Chatting with {username}'

    def _set_status(self, text: str) -> None:
        if self.shutting_down:
            return

        try:
            status = self.query_one('#status', Static)
        except NoMatches:
            return

        status.update(f'{text} | Ctrl+C to quit')

    def _write_system_message(self, text: str) -> None:
        self.query_one('#chat', ChatLog).append_message(
            ChatMessage(
                id=uuid4(),
                sender='ogham-chat',
                text=self._sanitize_text(text),
                created_at=datetime.now(UTC),
                is_system=True,
            )
        )

    def _sanitize_text(self, text: str) -> str:
        text = self.ANSI_ESCAPE_RE.sub('', text)
        return ''.join(
            ch
            for ch in text
            if ch == '\n' or ch == '\t' or ch == ' ' or ch.isprintable()
        )


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

    relay_parser = subparsers.add_parser(
        'relay', help='Join remote relay endpoint'
    )
    relay_parser.add_argument('--url', required=True)
    relay_parser.add_argument('--name', default='guest')

    args = parser.parse_args()

    if args.mode == 'host':
        return ChatConfig(
            mode='host', username=args.name, host='127.0.0.1', port=args.port
        )

    if args.mode == 'relay':
        return ChatConfig(mode='relay', username=args.name, relay_url=args.url)

    return ChatConfig(
        mode='join', username=args.name, host=args.host, port=args.port
    )


def main() -> None:
    config = parse_args()
    ChatApp(config).run()


if __name__ == '__main__':
    main()
