import asyncio
from typing import cast

from pydantic.dataclasses import dataclass
from textual import events
from textual.message import Message
from textual.widgets import TextArea

from frontend.commands import slash_command_completions


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

    async def on_key(self, event: events.Key) -> None:
        """Intercept keys to submit, insert newline, or run autocomplete."""
        composer = cast(TextArea, self)
        match event.name:
            case 'enter':
                event.prevent_default()
                event.stop()
                composer.post_message(ChatComposerSubmit(composer.text))
            case 'tab':
                if self._autocomplete_slash_command(composer):
                    event.prevent_default()
                    event.stop()
            case 'shift_enter':
                event.prevent_default()
                event.stop()
                composer.insert('\n')
            case _:
                return

    def _autocomplete_slash_command(self, composer: TextArea) -> bool:
        """Autocomplete slash command names and `/chat` user arguments."""
        text = composer.text
        stripped = text.strip()
        if not stripped.startswith('/') or stripped.startswith('//'):
            return False

        body = stripped[1:]
        command_token = body.split(maxsplit=1)[0].lower() if body else ''

        if command_token in {'chat', 'dm', 'peer'}:
            return self._autocomplete_chat_target(composer)

        if any(ch.isspace() for ch in body):
            return False

        matches = slash_command_completions(body)
        if not matches:
            composer.post_message(
                ChatComposerAutocomplete(
                    text=f'No slash command matches /{body} (try /help)'
                )
            )
            return True

        if len(matches) == 1:
            composer.text = f'/{matches[0]} '
            return True

        common_prefix = self._longest_common_prefix(matches)
        if len(common_prefix) > len(body):
            composer.text = f'/{common_prefix}'

        composer.post_message(
            ChatComposerAutocomplete(
                text='Matches: ' + ', '.join(f'/{match}' for match in matches)
            )
        )
        return True

    def _autocomplete_chat_target(self, composer: TextArea) -> bool:
        """Autocomplete the first argument for `/chat` and its aliases."""
        text = composer.text.strip('\n')
        stripped = text.strip()
        if not stripped.startswith('/'):
            return False

        body = stripped[1:]
        parts = body.split(maxsplit=1)
        if not parts:
            return False

        command_name = parts[0].lower()
        if command_name not in {'chat', 'dm', 'peer'}:
            return False

        if len(parts) == 1:
            if text.endswith(' '):
                target_prefix = ''
            else:
                # Still completing the command token itself.
                return False
        else:
            target_prefix = parts[1].strip()
            if ' ' in target_prefix:
                return False

        targets = getattr(self, '_chat_targets', [])
        if not targets:
            composer.post_message(
                ChatComposerAutocomplete(text='No known contacts to autocomplete')
            )
            return True

        cycle_users = getattr(self, '_chat_target_cycle', [])
        cycle_index = getattr(self, '_chat_target_cycle_index', -1)
        cycle_options = [f'/chat {user} ' for user in cycle_users]
        if cycle_options and text in cycle_options:
            next_index = (cycle_index + 1) % len(cycle_users)
            self._chat_target_cycle_index = next_index
            setattr(self, '_suppress_cycle_reset', True)
            composer.text = f'/chat {cycle_users[next_index]} '
            return True

        lowered_prefix = target_prefix.lower()
        matches = [
            user for user in targets if user.lower().startswith(lowered_prefix)
        ]

        if not matches:
            composer.post_message(
                ChatComposerAutocomplete(
                    text=f'No user matches {target_prefix or "(empty)"}'
                )
            )
            return True

        if len(matches) == 1:
            self._chat_target_cycle = [matches[0]]
            self._chat_target_cycle_index = 0
            setattr(self, '_suppress_cycle_reset', True)
            composer.text = f'/chat {matches[0]} '
            return True

        self._chat_target_cycle = matches
        self._chat_target_cycle_index = 0

        common_prefix = self._longest_common_prefix(matches)
        if len(common_prefix) > len(target_prefix):
            setattr(self, '_suppress_cycle_reset', True)
            composer.text = f'/chat {common_prefix}'
        else:
            setattr(self, '_suppress_cycle_reset', True)
            composer.text = f'/chat {matches[0]} '

        composer.post_message(
            ChatComposerAutocomplete(text='Users: ' + ', '.join(matches))
        )
        return True

    @staticmethod
    def _longest_common_prefix(values: list[str]) -> str:
        """Compute the longest common prefix for a non-empty list of strings."""
        prefix = values[0]
        for value in values[1:]:
            while not value.startswith(prefix) and prefix:
                prefix = prefix[:-1]
        return prefix


class ChatComposer(ComposerKeyActionMixin, TextArea):
    """Text input widget that emits submit and typing activity events."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize typing debounce state for composer events."""
        super().__init__(*args, **kwargs)
        self._typing_active = False
        self._typing_generation = 0
        self._typing_idle_task: asyncio.Task | None = None
        self._chat_targets: list[str] = []
        self._chat_target_cycle: list[str] = []
        self._chat_target_cycle_index = -1
        self._suppress_cycle_reset = False

    def set_chat_targets(self, users: list[str]) -> None:
        """Set usernames used for `/chat <user>` autocomplete."""
        self._chat_targets = sorted(set(users))
        self._chat_target_cycle = []
        self._chat_target_cycle_index = -1

    def _set_text_from_completion(self, value: str) -> None:
        """Apply completion text without resetting autocomplete cycle."""
        self._suppress_cycle_reset = True
        self.text = value

    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Emit typing on first input and schedule idle typing-off."""
        del event

        if self._suppress_cycle_reset:
            self._suppress_cycle_reset = False
        else:
            self._chat_target_cycle = []
            self._chat_target_cycle_index = -1

        stripped = self.text.strip()
        active = bool(stripped)
        slash_command_input = (  # True if input starts with a single slash
            stripped.startswith('/') and not
            stripped.startswith('//')
        )
        remote_typing_active = active and not slash_command_input

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
