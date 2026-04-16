#!/usr/bin/env python3
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Static, TextArea

from backend import ChatConfig, LocalChatBackend, RelayChatBackend
from backend.core.message import ChatMessage
from frontend.assets.style.theme import NOSTALGOS_12
from frontend.cli import parse_args
from frontend.components.chat_log import ChatLog
from frontend.components.composer import (
    ChatComposer,
    ChatComposerSubmit,
    ChatComposerTyping,
)
from frontend.components.contact_list import ContactList, ContactSelected


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
        self.active_peer: str | None = getattr(config, 'peer', None)
        self.seen_messages: set[UUID] = set()

        backend_cls = (
            RelayChatBackend if config.mode == 'relay' else LocalChatBackend
        )
        self.backend = backend_cls(
            config=config,
            on_message=self._on_network_message,
            on_status=self._set_status,
            on_typing=self._on_network_typing,
            on_user_list=self._on_user_list,
        )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Horizontal(
            ContactList(self_username=self.config.username, id='contacts'),
            Vertical(
                ChatLog(self_username=self.config.username, id='chat'),
                ChatComposer('', id='composer'),
                id='chat-column',
            ),
        )
        yield Static('', id='status')
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
        contacts = self.query_one('#contacts', ContactList)
        contacts.border_title = 'Contacts'
        self._set_status('Ready — select a contact to start chatting')

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
        content = self._sanitize_text(message.text).strip()
        composer.clear()

        if not content:
            return

        await self.backend.send(content, to=self.active_peer)
        await self.backend.send_typing(False, to=self.active_peer)

    async def on_chat_composer_typing(
        self, message: ChatComposerTyping
    ) -> None:
        await self.backend.send_typing(message.active, to=self.active_peer)

    def on_contact_selected(self, message: ContactSelected) -> None:
        self._set_active_peer(message.username)
        self.query_one('#composer', ChatComposer).focus()

    def _on_user_list(self, users: list[str]) -> None:
        if self.shutting_down:
            return
        self.query_one('#contacts', ContactList).update_users(users)

    def _on_network_message(self, message: ChatMessage) -> None:
        if self.shutting_down:
            return

        if message.message_id in self.seen_messages:
            return
        self.seen_messages.add(message.message_id)

        if not message.is_system:
            self._set_active_peer(message.sender)

        message.content = self._sanitize_text(message.content)

        chat = self.query_one('#chat', ChatLog)
        if not message.is_system:
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

        first_peer = self.active_peer is None
        if self.active_peer == username:
            return

        self.active_peer = username
        self.query_one(
            '#chat', ChatLog
        ).border_title = f'Chatting with {username}'

        if first_peer:
            self.query_one('#contacts').add_class('has-peer')
            self.query_one('#chat-column').add_class('has-peer')

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
                message_id=uuid4(),
                sender='ogham-chat',
                to=self.config.username,
                content=self._sanitize_text(text),
                created_at=datetime.now(UTC),
                is_system=True,
                metadata=None,
            )
        )

    def _sanitize_text(self, text: str) -> str:
        text = self.ANSI_ESCAPE_RE.sub('', text)
        return ''.join(
            ch
            for ch in text
            if ch == '\n' or ch == '\t' or ch == ' ' or ch.isprintable()
        )


def main() -> None:
    config = parse_args()
    ChatApp(config).run()


if __name__ == '__main__':
    main()
