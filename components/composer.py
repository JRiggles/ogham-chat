from dataclasses import dataclass
from typing import cast
import asyncio

from textual import events
from textual.message import Message
from textual.widgets import TextArea


@dataclass
class ChatComposerSubmit(Message):
    text: str

    def __post_init__(self) -> None:
        Message.__post_init__(self)


@dataclass
class ChatComposerTyping(Message):
    active: bool

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


class ChatComposer(EnterToSubmitMixin, TextArea):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._typing_active = False
        self._typing_generation = 0
        self._typing_idle_task: asyncio.Task | None = None

    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        del event
        active = bool(self.text.strip())
        if not active:
            self._typing_generation += 1
            if self._typing_idle_task is not None:
                self._typing_idle_task.cancel()
                self._typing_idle_task = None
            if self._typing_active:
                self._typing_active = False
                self.post_message(ChatComposerTyping(active=False))
            return

        if not self._typing_active:
            self._typing_active = True
            self.post_message(ChatComposerTyping(active=True))

        self._typing_generation += 1
        generation = self._typing_generation
        if self._typing_idle_task is not None:
            self._typing_idle_task.cancel()
        self._typing_idle_task = asyncio.create_task(
            self._emit_idle_stop(generation)
        )

    async def _emit_idle_stop(self, generation: int) -> None:
        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            return

        if generation != self._typing_generation:
            return

        if self._typing_active:
            self._typing_active = False
            self.post_message(ChatComposerTyping(active=False))

    async def on_unmount(self) -> None:
        if self._typing_idle_task is not None:
            self._typing_idle_task.cancel()
            self._typing_idle_task = None
