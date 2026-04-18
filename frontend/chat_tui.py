#!/usr/bin/env python3
import asyncio
import contextlib
import re
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Static, TextArea

from backend import (
    ChatConfig,
    LocalChatBackend,
    RelayChatBackend,
    RelayHistoryClient,
)
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
    """Textual chat application orchestrating backend events and UI state."""

    ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    REFRESH_UI_MIN_SECONDS = 0.5
    TITLE = 'Ogham Chat'
    SUB_TITLE = 'Local Terminal Relay'  # TODO: dynamic status? better sub?
    CSS_PATH = 'assets/style/chat.tcss'

    BINDINGS = [
        ('ctrl+c', 'quit', 'Quit'),
        ('ctrl+r', 'refresh', 'Refresh'),
    ]

    def __init__(self, config: ChatConfig) -> None:
        """Initialize UI state and select the transport backend."""
        super().__init__()
        self.config = config
        self.shutting_down = False
        self.active_peer: str | None = getattr(config, 'peer', None)
        self.seen_messages: set[UUID] = set()
        self.online_users: set[str] = set()
        self.known_contacts: set[str] = set()
        self.conversations: dict[str, list[ChatMessage]] = defaultdict(list)
        self.last_sync_at: datetime | None = None
        self.history_client: RelayHistoryClient | None = None
        self.sync_task: asyncio.Task[None] | None = None
        self.refresh_in_flight = False

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
        if config.mode == 'relay':
            self.history_client = RelayHistoryClient(
                config=config,
                on_status=self._set_status,
            )

    def compose(self) -> ComposeResult:
        """Compose the application layout widgets."""
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
        """Start backend services and initialize UI defaults on startup."""
        self.register_theme(NOSTALGOS_12)
        self.theme = 'nostalgos-12'

        await self.backend.start()

        await self._sync_recent_messages()
        if self.history_client is not None:
            self.sync_task = asyncio.create_task(self._sync_loop())
        if self.active_peer:
            await self._load_conversation(self.active_peer)

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
        """Shut down background tasks and backend connections."""
        self.shutting_down = True
        if self.sync_task is not None:
            self.sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.sync_task
            self.sync_task = None
        await self.backend.stop()

    def on_resize(self, event: events.Resize) -> None:
        """Re-render chat content after terminal resize events."""
        del event
        self.query_one('#chat', ChatLog).rerender()

    async def action_refresh(self) -> None:
        """Manually refresh history and keep status visible briefly."""
        if self.shutting_down:
            return

        if self.refresh_in_flight:
            return

        self.refresh_in_flight = True
        try:
            started_at = asyncio.get_running_loop().time()
            self._set_status('Refreshing history...')
            await self._refresh_history(manual=False)

            elapsed = asyncio.get_running_loop().time() - started_at
            remaining = self.REFRESH_UI_MIN_SECONDS - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)

            self._set_status('Refreshed')
            self.query_one('#composer', ChatComposer).focus()
        finally:
            self.refresh_in_flight = False

    async def on_chat_composer_submit(
        self, message: ChatComposerSubmit
    ) -> None:
        """Send submitted text as a message and stop typing indicators."""
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
        """Forward local typing-state changes to the backend transport."""
        await self.backend.send_typing(message.active, to=self.active_peer)

    async def on_contact_selected(self, message: ContactSelected) -> None:
        """Switch active conversation when a contact is selected."""
        self._set_active_peer(message.username)
        await self._load_conversation(message.username)
        self.query_one('#composer', ChatComposer).focus()

    def _on_user_list(self, users: list[str]) -> None:
        """Update online-user state from backend presence events."""
        if self.shutting_down:
            return

        self.online_users = {u for u in users if u != self.config.username}
        self._refresh_contacts()

    def _on_network_message(self, message: ChatMessage) -> None:
        """Handle one inbound network message and update conversation state."""
        if self.shutting_down:
            return

        message = self._normalize_message_timestamp(message)

        if message.message_id in self.seen_messages:
            return
        self.seen_messages.add(message.message_id)

        peer = self._peer_for_message(message)
        self._remember_contact(peer)
        self._store_message(message)

        if not message.is_system:
            self._set_active_peer(message.sender)

        message.content = self._sanitize_text(message.content)

        chat = self.query_one('#chat', ChatLog)
        if not message.is_system:
            chat.set_peer_typing(message.sender, False)
        if peer == self.active_peer:
            chat.set_messages(self.conversations.get(peer, []))

    def _on_network_typing(self, username: str, active: bool) -> None:
        """Reflect typing activity from a peer in the chat log."""
        if self.shutting_down:
            return

        self._set_active_peer(username)
        self.query_one('#chat', ChatLog).set_peer_typing(username, active)

    def _set_active_peer(self, username: str) -> None:
        """Set the active peer and refresh chat/contact panels."""
        if not username or username == self.config.username:
            return

        first_peer = self.active_peer is None
        if self.active_peer == username:
            return

        self.active_peer = username
        self._remember_contact(username)
        self.query_one(
            '#chat', ChatLog
        ).border_title = f'Chatting with {username}'
        self.query_one('#chat', ChatLog).set_messages(
            self.conversations.get(username, [])
        )

        if first_peer:
            self.query_one('#contacts').add_class('has-peer')
            self.query_one('#chat-column').add_class('has-peer')

    def _set_status(self, text: str) -> None:
        """Write a status line message with a quit hint."""
        if self.shutting_down:
            return

        try:
            status = self.query_one('#status', Static)
        except NoMatches:
            return

        status.update(f'{text} | Ctrl+C to quit')

    def _write_system_message(self, text: str) -> None:
        """Append a local synthetic system message to the chat log."""
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
        """Strip ANSI escapes and non-printable control characters."""
        text = self.ANSI_ESCAPE_RE.sub('', text)
        return ''.join(
            ch
            for ch in text
            if ch == '\n' or ch == '\t' or ch == ' ' or ch.isprintable()
        )

    def _remember_contact(self, username: str | None) -> None:
        """Track a discovered contact and refresh the contact list."""
        if not username or username == self.config.username:
            return
        self.known_contacts.add(username)
        self._refresh_contacts()

    def _refresh_contacts(self) -> None:
        """Render the current union of known and online contacts."""
        if self.shutting_down:
            return
        users = sorted(self.known_contacts | self.online_users)
        self.query_one('#contacts', ContactList).update_users(users)

    def _peer_for_message(self, message: ChatMessage) -> str:
        """Return the conversation peer key for a message."""
        return (
            message.to
            if message.sender == self.config.username
            else message.sender
        )

    def _store_message(self, message: ChatMessage) -> None:
        """Insert a message into conversation history with dedup and ordering."""
        message = self._normalize_message_timestamp(message)
        peer = self._peer_for_message(message)
        conversation = self.conversations[peer]
        if any(
            existing.message_id == message.message_id
            for existing in conversation
        ):
            return
        conversation.append(message)
        conversation.sort(
            key=lambda item: self._normalized_timestamp(item.created_at)
        )

    async def _sync_loop(self) -> None:
        """Periodically fetch recent history while the app is running."""
        while not self.shutting_down:
            await asyncio.sleep(5)
            await self._sync_recent_messages()

    async def _refresh_history(self, *, manual: bool = False) -> None:
        """Refresh incoming and active-conversation history from relay APIs."""
        await self._sync_recent_messages()

        if self.active_peer:
            await self._load_conversation(self.active_peer)

        if manual:
            if self.history_client is not None:
                self._set_status('Refresh complete')
            else:
                self._set_status('Local mode has no server history to refresh')

    async def _sync_recent_messages(self) -> None:
        """Fetch incoming relay messages and merge them into local state."""
        if self.history_client is None:
            return

        try:
            messages = await self.history_client.fetch_incoming_after(
                self.last_sync_at
            )
        except Exception as exc:
            self._set_status(f'History sync failed: {exc}')
            return

        self._merge_history(messages, update_sync_cursor=True)

    async def _load_conversation(self, peer_id: str) -> None:
        """Load full conversation history for the selected peer."""
        if self.history_client is None:
            return

        try:
            messages = await self.history_client.fetch_conversation(peer_id)
        except Exception as exc:
            self._set_status(f'Conversation load failed: {exc}')
            return

        self._merge_history(messages)
        if self.active_peer == peer_id:
            self.query_one('#chat', ChatLog).set_messages(
                self.conversations.get(peer_id, [])
            )

    def _merge_history(
        self,
        messages: list[ChatMessage],
        *,
        update_sync_cursor: bool = False,
    ) -> None:
        """Merge fetched history into local state while de-duplicating by id."""
        latest_seen_at = (
            self._normalized_timestamp(self.last_sync_at)
            if self.last_sync_at is not None
            else None
        )

        for message in messages:
            normalized_created_at = self._normalized_timestamp(
                message.created_at
            )
            if message.message_id in self.seen_messages:
                if (
                    latest_seen_at is None
                    or normalized_created_at > latest_seen_at
                ):
                    latest_seen_at = normalized_created_at
                continue

            sanitized = message.model_copy(
                update={
                    'content': self._sanitize_text(message.content),
                    'created_at': normalized_created_at,
                }
            )
            self.seen_messages.add(sanitized.message_id)
            self._remember_contact(self._peer_for_message(sanitized))
            self._store_message(sanitized)
            if (
                latest_seen_at is None
                or normalized_created_at > latest_seen_at
            ):
                latest_seen_at = normalized_created_at

        if update_sync_cursor:
            self.last_sync_at = latest_seen_at

        if self.active_peer:
            self.query_one('#chat', ChatLog).set_messages(
                self.conversations.get(self.active_peer, [])
            )

    def _normalize_message_timestamp(
        self, message: ChatMessage
    ) -> ChatMessage:
        """Return a message copy with UTC-normalized timestamp when needed."""
        normalized_created_at = self._normalized_timestamp(message.created_at)
        if normalized_created_at == message.created_at:
            return message
        return message.model_copy(update={'created_at': normalized_created_at})

    def _normalized_timestamp(self, value: datetime) -> datetime:
        """Normalize any datetime value into timezone-aware UTC."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def main() -> None:
    """Parse CLI args and launch the Textual chat application."""
    config = parse_args()
    ChatApp(config).run()


if __name__ == '__main__':
    main()
