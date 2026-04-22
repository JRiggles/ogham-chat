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

    @staticmethod
    def _has_slash_command_prefix(text: str) -> bool:
        """Return True when text begins with a single slash command prefix."""
        normalized = text.lstrip()
        return normalized.startswith('/') and not normalized.startswith('//')

    @property
    def command_mode_active(self) -> bool:
        """Whether slash-command mode is currently active."""
        return bool(getattr(self, '_command_mode_active', False))

    @command_mode_active.setter
    def command_mode_active(self, value: bool) -> None:
        """Set slash-command mode state."""
        self._command_mode_active = value

    async def on_key(self, event: events.Key) -> None:
        """Intercept keys to submit, insert newline, or run autocomplete."""
        composer = cast(TextArea, self)
        stripped = composer.text.strip()
        if not stripped:  # composer is empty or whitespace-only
            self.command_mode_active = False
        elif not self.command_mode_active:
            self.command_mode_active = self._has_slash_command_prefix(
                composer.text
            )
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

    def _autocomplete_slash_command(
        self, composer: TextArea, *, reverse: bool = False
    ) -> bool:
        """Autocomplete slash command names and `/chat` user arguments."""
        stripped = composer.text.strip()
        if not stripped:
            self.command_mode_active = False
        elif not self.command_mode_active:
            self.command_mode_active = self._has_slash_command_prefix(
                composer.text
            )
        command_mode_active = self.command_mode_active
        completion_text = (
            composer.text.lstrip() if command_mode_active else composer.text
        )
        _suggester: ComposerSuggester | None = getattr(
            self, '_composer_suggester', None
        )
        result = autocomplete_slash_input(
            text=completion_text,
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
            composer.post_message(
                ChatComposerAutocomplete(text=result.status_text)
            )

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
        self._command_mode_active = False
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

        stripped = self.text.strip()
        if not stripped:
            self.command_mode_active = False
        elif not self.command_mode_active:
            self.command_mode_active = self._has_slash_command_prefix(
                self.text
            )
        command_mode_active = self.command_mode_active
        self.set_class(command_mode_active, 'command-mode')

        if self._suppress_cycle_reset:
            self._suppress_cycle_reset = False
        else:
            self._autocomplete_cycle_options = []
            self._autocomplete_cycle_index = -1

        suggestion_text = (
            self.text.lstrip() if command_mode_active else self.text
        )
        full_suggestion = await self._composer_suggester.get_suggestion(
            suggestion_text
        )
        self.suggestion = (
            full_suggestion[len(suggestion_text) :]
            if full_suggestion is not None
            else ''
        )

        active = bool(stripped)
        remote_typing_active = active and not command_mode_active

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
