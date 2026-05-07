from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from datetime import datetime

from backend import (
    ChatConfig,
    LocalChatBackend,
    RelayChatBackend,
    RelayHistoryClient,
)
from backend.core.message import ChatMessage

HistorySink = Callable[[list[ChatMessage]], None]
StatusSink = Callable[[str, str | None], None]
TimestampNormalizer = Callable[[datetime], datetime]


class ChatSessionRuntime:
    """Own transport lifecycle, history fetches, and background sync."""

    def __init__(
        self,
        config: ChatConfig,
        on_message: Callable[[ChatMessage], None],
        on_status: StatusSink,
        on_typing: Callable[[str, bool], None],
        on_user_list: Callable[[list[str]], None],
        normalize_timestamp: TimestampNormalizer,
    ) -> None:
        self.config = config
        self.on_message = on_message
        self.on_status = on_status
        self.on_typing = on_typing
        self.on_user_list = on_user_list
        self.normalize_timestamp = normalize_timestamp

        self.backend: RelayChatBackend | LocalChatBackend | None = None
        self.history_client: RelayHistoryClient | None = None
        self.last_sync_at: datetime | None = None
        self.sync_task: asyncio.Task[None] | None = None
        self._history_sink: HistorySink | None = None

        self._configure_runtime_backends()

    @property
    def history_available(self) -> bool:
        """Return whether relay-backed history APIs are available."""
        return self.history_client is not None

    async def start(
        self,
        *,
        active_peer: str | None,
        on_history: HistorySink,
    ) -> None:
        """Start transports, perform initial sync, and schedule history polling."""
        self._history_sink = on_history

        if self.backend is None:
            self._configure_runtime_backends()

        assert self.backend is not None
        await self.backend.start()

        await self._sync_recent_messages()
        if self.history_client is not None and self.sync_task is None:
            self.sync_task = asyncio.create_task(self._sync_loop())
        if active_peer:
            await self.load_conversation(active_peer)

    async def stop(self) -> None:
        """Stop background sync and close the active transport backend."""
        if self.sync_task is not None:
            self.sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.sync_task
            self.sync_task = None

        self._history_sink = None

        if self.backend is not None:
            await self.backend.stop()

    async def send(
        self, content: str, to: str | None = None, metadata: dict | None = None
    ) -> None:
        """Forward one outbound chat message to the active backend."""
        if self.backend is not None:
            await self.backend.send(content, to=to, metadata=metadata)

    async def send_typing(self, active: bool, to: str | None = None) -> None:
        """Forward one typing-state update to the active backend."""
        if self.backend is not None:
            await self.backend.send_typing(active, to=to)

    async def refresh_history(self, *, active_peer: str | None) -> None:
        """Refresh incoming history and the active conversation, if any."""
        await self._sync_recent_messages()
        if active_peer:
            await self.load_conversation(active_peer)

    async def load_conversation(self, peer_id: str) -> None:
        """Load full conversation history for one selected peer."""
        if self.history_client is None:
            return

        try:
            messages = await self.history_client.fetch_conversation(peer_id)
        except Exception as exc:
            self.on_status(f'Conversation load failed: {exc}', '$error')
            return

        self._publish_history(messages)

    def _configure_runtime_backends(self) -> None:
        """Instantiate transport backends from the current app config."""
        backend_cls = (
            RelayChatBackend
            if self.config.mode == 'relay'
            else LocalChatBackend
        )
        self.backend = backend_cls(
            config=self.config,
            on_message=self.on_message,
            on_status=self._on_transport_status,
            on_typing=self.on_typing,
            on_user_list=self.on_user_list,
        )
        if self.config.mode == 'relay':
            self.history_client = RelayHistoryClient(
                config=self.config,
                on_status=self._on_transport_status,
            )
        else:
            self.history_client = None

    async def _sync_loop(self) -> None:
        """Periodically fetch recent history while the app is running."""
        while True:
            await asyncio.sleep(5)
            await self._sync_recent_messages()

    async def _sync_recent_messages(self) -> None:
        """Fetch incoming history and publish it to the UI state sink."""
        if self.history_client is None:
            return

        try:
            messages = await self.history_client.fetch_incoming_after(
                self.last_sync_at
            )
        except Exception as exc:
            self.on_status(f'Chat history sync failed: {exc}', '$error')
            return

        self._advance_sync_cursor(messages)
        self._publish_history(messages)

    def _advance_sync_cursor(self, messages: list[ChatMessage]) -> None:
        """Advance the incremental history cursor from fetched messages."""
        if not messages:
            return

        latest_seen_at = max(
            self.normalize_timestamp(message.created_at)
            for message in messages
        )
        if self.last_sync_at is None or latest_seen_at > self.last_sync_at:
            self.last_sync_at = latest_seen_at

    def _publish_history(self, messages: list[ChatMessage]) -> None:
        """Forward fetched history into the app's local merge pipeline."""
        if self._history_sink is None:
            return
        self._history_sink(messages)

    def _on_transport_status(self, text: str) -> None:
        """Adapt plain transport status updates to the UI status sink."""
        self.on_status(text, None)
