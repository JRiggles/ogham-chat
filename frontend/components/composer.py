import asyncio
from typing import cast

from pydantic.dataclasses import dataclass
from textual import events
from textual.message import Message
from textual.widgets import TextArea


@dataclass
class ChatComposerSubmit(Message):
    """Event emitted when the user submits composer text."""

    text: str

    def __post_init__(self) -> None:
        Message.__post_init__(self)


@dataclass
class ChatComposerTyping(Message):
    """Event emitted when typing activity toggles."""

    active: bool

    def __post_init__(self) -> None:
        Message.__post_init__(self)


class EnterToSubmitMixin:
    """Mixin that maps Enter/Shift+Enter into submit/newline behavior."""

    async def on_key(self, event: events.Key) -> None:
        """Intercept key presses and emit submit/newline actions."""
        composer = cast(TextArea, self)
        match event.name:
            case 'enter':
                event.prevent_default()
                event.stop()
                composer.post_message(ChatComposerSubmit(composer.text))
            case 'shift_enter':
                event.prevent_default()
                event.stop()
                composer.insert('\n')
            case _:
                return


class ChatComposer(EnterToSubmitMixin, TextArea):
    """Text input widget that emits submit and typing activity events."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize typing debounce state for composer events."""
        super().__init__(*args, **kwargs)
        self._typing_active = False
        self._typing_generation = 0
        self._typing_idle_task: asyncio.Task | None = None

    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Emit typing on first input and schedule idle typing-off."""
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
        """Emit typing-off when no newer keystroke arrives before timeout."""
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
        """Cancel pending typing debounce work during widget teardown."""
        if self._typing_idle_task is not None:
            self._typing_idle_task.cancel()
            self._typing_idle_task = None
