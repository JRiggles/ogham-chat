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


def _normalize_match_token(value: str) -> str:
    """Normalize one token for forgiving autocomplete matching."""
    return value.lower().replace('-', '').replace('_', '')


def _target_matches_prefix(target: str, prefix: str) -> bool:
    """Return whether a completion target matches a typed prefix."""
    return _normalize_match_token(target).startswith(
        _normalize_match_token(prefix)
    )


def _has_immediate_command_token(body: str) -> bool:
    """Return True when command text starts immediately after '/'."""
    return bool(body) and not body[0].isspace()


def _parse_slash_body(text: str) -> tuple[str, str] | None:
    """Return normalized text and slash-command body when input is command-like."""
    text_no_newline = text.strip('\n')
    stripped = text_no_newline.strip()
    if (
        not stripped.startswith('/')
        or stripped.startswith('//')
        or not _has_immediate_command_token(stripped[1:])
    ):
        return None

    return text_no_newline, stripped[1:]


def _parse_target_prefix(
    *, text: str, command_aliases: set[str]
) -> tuple[str, str] | None:
    """Return normalized text and first target prefix for a command alias set."""
    parsed = _parse_slash_body(text)
    if parsed is None:
        return None

    text_no_newline, body = parsed
    parts = body.split(maxsplit=1)
    match parts:
        case [command] if command.lower() in command_aliases:
            if text_no_newline.endswith(' '):
                return text_no_newline, ''
            return None
        case [command, raw_target] if command.lower() in command_aliases:
            target_prefix = raw_target.strip()
            if ' ' in target_prefix:
                return None
            return text_no_newline, target_prefix
        case _:
            return None


def _resolve_cycle_option(
    *,
    text_no_newline: str,
    candidate_options: list[str],
    cycle_options: list[str],
    cycle_index: int,
    reverse: bool,
) -> tuple[str, list[str], int]:
    """Choose next autocomplete option from candidates or active cycle state."""
    if cycle_options and text_no_newline in cycle_options:
        step = -1 if reverse else 1
        next_index = (cycle_index + step) % len(cycle_options)
        return cycle_options[next_index], cycle_options, next_index

    return candidate_options[0], candidate_options, 0


def _autocomplete_target_argument(
    *,
    text: str,
    targets: list[str],
    cycle_options: list[str],
    cycle_index: int,
    reverse: bool,
    command_aliases: set[str],
    canonical_command: str,
    no_targets_status: str,
    no_match_noun: str,
    list_status_prefix: str,
) -> ComposerAutocompleteResult:
    """Autocomplete a first command argument from candidate targets."""
    parsed = _parse_target_prefix(text=text, command_aliases=command_aliases)
    if parsed is None:
        return ComposerAutocompleteResult(handled=False)

    text_no_newline, target_prefix = parsed
    if not targets:
        return ComposerAutocompleteResult(
            handled=True,
            status_text=no_targets_status,
        )

    matches = [
        target
        for target in targets
        if _target_matches_prefix(target, target_prefix)
    ]

    if not matches:
        return ComposerAutocompleteResult(
            handled=True,
            status_text=f'No {no_match_noun} matches {target_prefix or "(empty)"}',
        )

    if len(matches) == 1:
        return ComposerAutocompleteResult(
            handled=True,
            new_text=f'/{canonical_command} {matches[0]} ',
        )

    candidate_options = [
        f'/{canonical_command} {target} ' for target in matches
    ]
    next_text, next_cycle_options, next_index = _resolve_cycle_option(
        text_no_newline=text_no_newline,
        candidate_options=candidate_options,
        cycle_options=cycle_options,
        cycle_index=cycle_index,
        reverse=reverse,
    )

    return ComposerAutocompleteResult(
        handled=True,
        new_text=next_text,
        status_text=f'{list_status_prefix}: ' + ', '.join(matches),
        suppress_cycle_reset=True,
        cycle_options=next_cycle_options,
        cycle_index=next_index,
    )


def _target_argument_suggestion(
    *, text: str, targets: list[str], command_aliases: set[str]
) -> str:
    """Return ghost-text suffix for a command's first argument."""
    parsed = _parse_target_prefix(text=text, command_aliases=command_aliases)
    if parsed is None:
        return ''

    _, target_prefix = parsed
    matches = [
        target
        for target in targets
        if _target_matches_prefix(target, target_prefix)
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
    parsed = _parse_slash_body(text)
    if parsed is None:
        return ComposerAutocompleteResult(handled=False)

    text_no_newline, body = parsed

    command_token = body.split(maxsplit=1)[0].lower() if body else ''

    match command_token:
        case 'chat' | 'dm':
            return _autocomplete_chat_target(
                text=text,
                targets=chat_targets,
                cycle_options=cycle_options,
                cycle_index=cycle_index,
                reverse=reverse,
            )
        case 'theme' | 't':
            return _autocomplete_theme_target(
                text=text,
                targets=theme_targets,
                cycle_options=cycle_options,
                cycle_index=cycle_index,
                reverse=reverse,
            )
        case _:
            pass

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
    next_text, next_cycle_options, next_index = _resolve_cycle_option(
        text_no_newline=text_no_newline,
        candidate_options=candidate_options,
        cycle_options=cycle_options,
        cycle_index=cycle_index,
        reverse=reverse,
    )

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
    parsed = _parse_slash_body(text)
    if parsed is None:
        return ''

    _, body = parsed

    command_token = body.split(maxsplit=1)[0].lower() if body else ''

    match command_token:
        case 'chat' | 'dm':
            return _chat_target_suggestion(text=text, targets=chat_targets)
        case 'theme' | 't':
            return _theme_target_suggestion(text=text, targets=theme_targets)
        case _:
            pass

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
    return _autocomplete_target_argument(
        text=text,
        targets=targets,
        cycle_options=cycle_options,
        cycle_index=cycle_index,
        reverse=reverse,
        command_aliases={'chat', 'dm'},
        canonical_command='chat',
        no_targets_status='No known contacts to autocomplete',
        no_match_noun='user',
        list_status_prefix='Users',
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
    return _autocomplete_target_argument(
        text=text,
        targets=targets,
        cycle_options=cycle_options,
        cycle_index=cycle_index,
        reverse=reverse,
        command_aliases={'theme', 't'},
        canonical_command='theme',
        no_targets_status='No known themes to autocomplete',
        no_match_noun='theme',
        list_status_prefix='Themes',
    )


def _chat_target_suggestion(*, text: str, targets: list[str]) -> str:
    """Return ghost-text suffix for /chat target completion."""
    return _target_argument_suggestion(
        text=text,
        targets=targets,
        command_aliases={'chat', 'dm'},
    )


def _theme_target_suggestion(*, text: str, targets: list[str]) -> str:
    """Return ghost-text suffix for /theme target completion."""
    return _target_argument_suggestion(
        text=text,
        targets=targets,
        command_aliases={'theme', 't'},
    )


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
