import asyncio
from typing import cast

from pydantic.dataclasses import dataclass
from textual import events
from textual.message import Message
from textual.widgets import TextArea

from frontend.commands import slash_command_completions
from frontend.components.autocomplete import (
    ComposerSuggester,
    autocomplete_slash_input,
)


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


@dataclass
class ChatComposerAutocomplete(Message):
    """Event emitted when slash autocomplete has a user-facing hint."""

    text: str

    def __post_init__(self) -> None:
        Message.__post_init__(self)


class ComposerKeyActionMixin:
    """Mixin that handles composer key actions and slash autocomplete."""

    @property
    def _is_slash_input(self) -> bool:
        """True if the current text is a slash command (not an escaped //)."""
        text = cast(TextArea, self).text.strip()
        return text.startswith('/') and not text.startswith('//')

    async def on_key(self, event: events.Key) -> None:
        """Intercept keys to submit, insert newline, or run autocomplete."""
        composer = cast(TextArea, self)
        match event.name:
            case 'enter':
                event.prevent_default()
                event.stop()
                composer.post_message(ChatComposerSubmit(composer.text))
            case 'up' | 'down' if self._is_slash_input:
                event.prevent_default()
                event.stop()
                self._autocomplete_slash_command(composer, reverse=event.name == 'up')
            case 'shift_enter':
                event.prevent_default()
                event.stop()
                composer.insert('\n')
            case _:
                return

    def _autocomplete_slash_command(
        self, composer: TextArea, *, reverse: bool = False
    ) -> bool:
        """Autocomplete slash command names and `/chat` user arguments."""
        _suggester: ComposerSuggester | None = getattr(
            self, '_composer_suggester', None
        )
        result = autocomplete_slash_input(
            text=composer.text,
            command_completions=slash_command_completions,
            chat_targets=_suggester._chat_targets if _suggester else [],
            theme_targets=_suggester._theme_targets if _suggester else [],
            cycle_options=getattr(self, '_autocomplete_cycle_options', []),
            cycle_index=getattr(self, '_autocomplete_cycle_index', -1),
            reverse=reverse,
        )
        if not result.handled:
            return False

        if result.cycle_options is not None:
            self._autocomplete_cycle_options = result.cycle_options
        if result.cycle_index is not None:
            self._autocomplete_cycle_index = result.cycle_index

        if result.new_text is not None:
            if result.suppress_cycle_reset:
                setattr(self, '_suppress_cycle_reset', True)
                composer.text = result.new_text
            else:
                composer.text = result.new_text

        if result.status_text:
            composer.post_message(ChatComposerAutocomplete(text=result.status_text))

        return True


class ChatComposer(ComposerKeyActionMixin, TextArea):
    """Text input widget that emits submit and typing activity events."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize typing debounce state for composer events."""
        kwargs.setdefault('tab_behavior', 'indent')
        super().__init__(*args, **kwargs)
        self._typing_active = False
        self._typing_generation = 0
        self._typing_idle_task: asyncio.Task | None = None
        self._composer_suggester = ComposerSuggester(
            command_completions=slash_command_completions
        )
        self._autocomplete_cycle_options: list[str] = []
        self._autocomplete_cycle_index = -1
        self._suppress_cycle_reset = False

    def set_chat_targets(self, users: list[str]) -> None:
        """Set usernames used for `/chat <user>` autocomplete."""
        self._composer_suggester.update_chat_targets(users)
        self._autocomplete_cycle_options = []
        self._autocomplete_cycle_index = -1

    def set_theme_targets(self, themes: list[str]) -> None:
        """Set theme names used for `/theme <name>` autocomplete."""
        self._composer_suggester.update_theme_targets(themes)

    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Emit typing on first input and schedule idle typing-off."""
        del event

        if self._suppress_cycle_reset:
            self._suppress_cycle_reset = False
        else:
            self._autocomplete_cycle_options = []
            self._autocomplete_cycle_index = -1

        full_suggestion = await self._composer_suggester.get_suggestion(self.text)
        self.suggestion = (
            full_suggestion[len(self.text) :] if full_suggestion is not None else ''
        )

        stripped = self.text.strip()
        active = bool(stripped)
        remote_typing_active = active and not self._is_slash_input

        if not remote_typing_active:
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

        self._typing_idle_task = asyncio.create_task(self._emit_idle_stop(generation))

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
