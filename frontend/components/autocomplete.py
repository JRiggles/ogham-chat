from collections.abc import Callable
from dataclasses import dataclass

from textual.suggester import Suggester


@dataclass
class ComposerAutocompleteResult:
    """Result payload for one autocomplete request."""

    handled: bool
    new_text: str | None = None
    status_text: str | None = None
    suppress_cycle_reset: bool = False
    cycle_options: list[str] | None = None
    cycle_index: int | None = None


def _longest_common_prefix(values: list[str]) -> str:
    """Compute the longest common prefix for a non-empty list of strings."""
    prefix = values[0]
    for value in values[1:]:
        while not value.startswith(prefix) and prefix:
            prefix = prefix[:-1]
    return prefix


def autocomplete_slash_input(
    *,
    text: str,
    command_completions: Callable[[str], list[str]],
    chat_targets: list[str],
    theme_targets: list[str],
    cycle_options: list[str],
    cycle_index: int,
    reverse: bool = False,
) -> ComposerAutocompleteResult:
    """Autocomplete slash command names and supported command arguments."""
    text_no_newline = text.strip('\n')
    stripped = text.strip()
    if not stripped.startswith('/') or stripped.startswith('//'):
        return ComposerAutocompleteResult(handled=False)

    body = stripped[1:]
    command_token = body.split(maxsplit=1)[0].lower() if body else ''

    if command_token in {'chat', 'dm', 'peer'}:
        return _autocomplete_chat_target(
            text=text,
            targets=chat_targets,
            cycle_options=cycle_options,
            cycle_index=cycle_index,
            reverse=reverse,
        )

    if command_token in {'theme', 't'}:
        return _autocomplete_theme_target(
            text=text,
            targets=theme_targets,
            cycle_options=cycle_options,
            cycle_index=cycle_index,
            reverse=reverse,
        )

    if any(ch.isspace() for ch in body):
        return ComposerAutocompleteResult(handled=False)

    matches = command_completions(body)
    if not matches:
        return ComposerAutocompleteResult(
            handled=True,
            status_text=f'No slash command matches /{body} (try /help)',
        )

    if len(matches) == 1:
        return ComposerAutocompleteResult(
            handled=True, new_text=f'/{matches[0]} '
        )

    candidate_options = [f'/{match} ' for match in matches]
    if cycle_options and text_no_newline in cycle_options:
        step = -1 if reverse else 1
        next_index = (cycle_index + step) % len(cycle_options)
        next_text = cycle_options[next_index]
        next_cycle_options = cycle_options
    else:
        next_index = 0
        next_text = candidate_options[0]
        next_cycle_options = candidate_options

    return ComposerAutocompleteResult(
        handled=True,
        new_text=next_text,
        status_text='Matches: ' + ', '.join(f'/{match}' for match in matches),
        suppress_cycle_reset=True,
        cycle_options=next_cycle_options,
        cycle_index=next_index,
    )


def _slash_input_suggestion(
    *,
    text: str,
    command_completions: Callable[[str], list[str]],
    chat_targets: list[str],
    theme_targets: list[str],
) -> str:
    """Return ghost-text suffix for the current slash input, if any."""
    stripped = text.strip()
    if not stripped.startswith('/') or stripped.startswith('//'):
        return ''

    body = stripped[1:]
    command_token = body.split(maxsplit=1)[0].lower() if body else ''

    if command_token in {'chat', 'dm', 'peer'}:
        return _chat_target_suggestion(text=text, targets=chat_targets)

    if command_token in {'theme', 't'}:
        return _theme_target_suggestion(text=text, targets=theme_targets)

    if any(ch.isspace() for ch in body):
        return ''

    matches = command_completions(body)
    if not matches:
        return ''

    if len(matches) == 1:
        match = matches[0]
        if match.startswith(body):
            suffix = match[len(body) :]
            return f'{suffix} '
        return ''

    common_prefix = _longest_common_prefix(matches)
    if len(common_prefix) > len(body):
        return common_prefix[len(body) :]

    return ''


def _autocomplete_chat_target(
    *,
    text: str,
    targets: list[str],
    cycle_options: list[str],
    cycle_index: int,
    reverse: bool = False,
) -> ComposerAutocompleteResult:
    """Autocomplete the first argument for /chat and its aliases."""
    text_no_newline = text.strip('\n')
    stripped = text_no_newline.strip()
    if not stripped.startswith('/'):
        return ComposerAutocompleteResult(handled=False)

    body = stripped[1:]
    parts = body.split(maxsplit=1)
    if not parts:
        return ComposerAutocompleteResult(handled=False)

    command_name = parts[0].lower()
    if command_name not in {'chat', 'dm', 'peer'}:
        return ComposerAutocompleteResult(handled=False)

    if len(parts) == 1:
        if text_no_newline.endswith(' '):
            target_prefix = ''
        else:
            return ComposerAutocompleteResult(handled=False)
    else:
        target_prefix = parts[1].strip()
        if ' ' in target_prefix:
            return ComposerAutocompleteResult(handled=False)

    if not targets:
        return ComposerAutocompleteResult(
            handled=True,
            status_text='No known contacts to autocomplete',
        )

    lowered_prefix = target_prefix.lower()
    matches = [
        user for user in targets if user.lower().startswith(lowered_prefix)
    ]

    if not matches:
        return ComposerAutocompleteResult(
            handled=True,
            status_text=f'No user matches {target_prefix or "(empty)"}',
        )

    if len(matches) == 1:
        return ComposerAutocompleteResult(
            handled=True,
            new_text=f'/chat {matches[0]} ',
        )

    candidate_options = [f'/chat {user} ' for user in matches]
    if cycle_options and text_no_newline in cycle_options:
        step = -1 if reverse else 1
        next_index = (cycle_index + step) % len(cycle_options)
        return ComposerAutocompleteResult(
            handled=True,
            new_text=cycle_options[next_index],
            suppress_cycle_reset=True,
            cycle_options=cycle_options,
            cycle_index=next_index,
        )

    next_index = 0
    next_text = candidate_options[0]

    return ComposerAutocompleteResult(
        handled=True,
        new_text=next_text,
        status_text='Users: ' + ', '.join(matches),
        suppress_cycle_reset=True,
        cycle_options=candidate_options,
        cycle_index=next_index,
    )


def _autocomplete_theme_target(
    *,
    text: str,
    targets: list[str],
    cycle_options: list[str],
    cycle_index: int,
    reverse: bool = False,
) -> ComposerAutocompleteResult:
    """Autocomplete the first argument for /theme and its alias."""
    text_no_newline = text.strip('\n')
    stripped = text_no_newline.strip()
    if not stripped.startswith('/'):
        return ComposerAutocompleteResult(handled=False)

    body = stripped[1:]
    parts = body.split(maxsplit=1)
    if not parts:
        return ComposerAutocompleteResult(handled=False)

    command_name = parts[0].lower()
    if command_name not in {'theme', 't'}:
        return ComposerAutocompleteResult(handled=False)

    if len(parts) == 1:
        if text_no_newline.endswith(' '):
            target_prefix = ''
        else:
            return ComposerAutocompleteResult(handled=False)
    else:
        target_prefix = parts[1].strip()
        if ' ' in target_prefix:
            return ComposerAutocompleteResult(handled=False)

    if not targets:
        return ComposerAutocompleteResult(
            handled=True,
            status_text='No known themes to autocomplete',
        )

    lowered_prefix = target_prefix.lower()
    matches = [
        theme for theme in targets if theme.lower().startswith(lowered_prefix)
    ]

    if not matches:
        return ComposerAutocompleteResult(
            handled=True,
            status_text=f'No theme matches {target_prefix or "(empty)"}',
        )

    if len(matches) == 1:
        return ComposerAutocompleteResult(
            handled=True,
            new_text=f'/theme {matches[0]} ',
        )

    candidate_options = [f'/theme {theme} ' for theme in matches]
    if cycle_options and text_no_newline in cycle_options:
        step = -1 if reverse else 1
        next_index = (cycle_index + step) % len(cycle_options)
        next_text = cycle_options[next_index]
        next_cycle_options = cycle_options
    else:
        next_index = 0
        next_text = candidate_options[0]
        next_cycle_options = candidate_options

    return ComposerAutocompleteResult(
        handled=True,
        new_text=next_text,
        status_text='Themes: ' + ', '.join(matches),
        suppress_cycle_reset=True,
        cycle_options=next_cycle_options,
        cycle_index=next_index,
    )


def _chat_target_suggestion(*, text: str, targets: list[str]) -> str:
    """Return ghost-text suffix for /chat target completion."""
    text_no_newline = text.strip('\n')
    stripped = text_no_newline.strip()
    if not stripped.startswith('/'):
        return ''

    body = stripped[1:]
    parts = body.split(maxsplit=1)
    if not parts:
        return ''

    command_name = parts[0].lower()
    if command_name not in {'chat', 'dm', 'peer'}:
        return ''

    if len(parts) == 1:
        if text_no_newline.endswith(' '):
            target_prefix = ''
        else:
            return ''
    else:
        target_prefix = parts[1].strip()
        if ' ' in target_prefix:
            return ''

    matches = [
        user
        for user in targets
        if user.lower().startswith(target_prefix.lower())
    ]
    if not matches:
        return ''

    if len(matches) == 1:
        match = matches[0]
        if match.startswith(target_prefix):
            return f'{match[len(target_prefix) :]} '
        return ''

    common_prefix = _longest_common_prefix(matches)
    if len(common_prefix) > len(target_prefix):
        return common_prefix[len(target_prefix) :]

    return ''


def _theme_target_suggestion(*, text: str, targets: list[str]) -> str:
    """Return ghost-text suffix for /theme target completion."""
    text_no_newline = text.strip('\n')
    stripped = text_no_newline.strip()
    if not stripped.startswith('/'):
        return ''

    body = stripped[1:]
    parts = body.split(maxsplit=1)
    if not parts:
        return ''

    command_name = parts[0].lower()
    if command_name not in {'theme', 't'}:
        return ''

    if len(parts) == 1:
        if text_no_newline.endswith(' '):
            target_prefix = ''
        else:
            return ''
    else:
        target_prefix = parts[1].strip()
        if ' ' in target_prefix:
            return ''

    matches = [
        theme
        for theme in targets
        if theme.lower().startswith(target_prefix.lower())
    ]
    if not matches:
        return ''

    if len(matches) == 1:
        match = matches[0]
        if match.startswith(target_prefix):
            return f'{match[len(target_prefix) :]} '
        return ''

    common_prefix = _longest_common_prefix(matches)
    if len(common_prefix) > len(target_prefix):
        return common_prefix[len(target_prefix) :]

    return ''


class ComposerSuggester(Suggester):
    """Provides slash-command ghost-text suggestions for the chat composer.

    Pass an instance to `ChatComposer` so the widget can display inline
    completion hints via `TextArea.suggestion`.
    """

    def __init__(
        self, *, command_completions: Callable[[str], list[str]]
    ) -> None:
        super().__init__(use_cache=False, case_sensitive=True)
        self._command_completions = command_completions
        self._chat_targets: list[str] = []
        self._theme_targets: list[str] = []

    def update_chat_targets(self, users: list[str]) -> None:
        """Replace the list of known chat targets."""
        self._chat_targets = sorted(set(users))

    def update_theme_targets(self, themes: list[str]) -> None:
        """Replace the list of known theme names."""
        self._theme_targets = sorted(set(themes), key=str.lower)

    async def get_suggestion(self, value: str) -> str | None:
        """Return the full suggested text for *value*, or None.

        The returned string starts with *value* extended by the longest
        unambiguous completion suffix. The caller derives the ghost-text
        suffix via ``result[len(value):]``.
        """
        suffix = _slash_input_suggestion(
            text=value,
            command_completions=self._command_completions,
            chat_targets=self._chat_targets,
            theme_targets=self._theme_targets,
        )
        return (value + suffix) if suffix else None
