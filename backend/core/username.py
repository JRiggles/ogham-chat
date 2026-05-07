import re

MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 24
RESERVED_USERNAMES = frozenset(
    {
        'ogham',
        'ogham-chat',
        'system',
    }
)

_ALLOWED_USERNAME_RE = re.compile(r'^[a-z][a-z0-9_-]*$')
USERNAME_RULES_SUMMARY = (
    'Your username must satisfy the following rules:'
)
USERNAME_REQUIREMENTS_LINES: tuple[str, ...] = (
    f'- {MIN_USERNAME_LENGTH} to {MAX_USERNAME_LENGTH} characters',
    '- must start with a letter',
    '- lowercase letters, digits, hyphens, and underscores only',
    '- cannot end with a hyphen or underscore',
    '- cannot contain consecutive hyphens or underscores,\n  (such as "--", ' '"__", "_-", or "-_")',
)


class UsernameValidationError(ValueError):
    """Raised when a username does not satisfy the app's policy."""


def username_requirements_text(*, prefix: str = '') -> str:
    """Return a multi-line human-readable summary of username rules."""
    if not prefix:
        return '\n'.join(USERNAME_REQUIREMENTS_LINES)
    return '\n'.join(
        f'{prefix}{line[2:]}' for line in USERNAME_REQUIREMENTS_LINES
    )


def validate_username(value: str) -> str:
    """Validate and normalize one username string.

    Leading and trailing whitespace are trimmed. Any other non-canonical input
    is rejected instead of being silently rewritten.
    """
    normalized = value.strip()

    if len(normalized) < MIN_USERNAME_LENGTH:
        raise UsernameValidationError(
            f'Your username must be at least {MIN_USERNAME_LENGTH} characters'
        )

    if len(normalized) > MAX_USERNAME_LENGTH:
        raise UsernameValidationError(
            f'Your username must be at most {MAX_USERNAME_LENGTH} characters'
        )

    if normalized.lower() != normalized:
        raise UsernameValidationError(
            'Your username must use lowercase letters only'
        )

    if not _ALLOWED_USERNAME_RE.fullmatch(normalized):
        raise UsernameValidationError(
            'This username does not meet the above requirements'
        )

    if normalized[-1] in {'-', '_'}:
        raise UsernameValidationError(
            'Your username cannot end with a hyphen or underscore'
        )

    if any(pair in normalized for pair in ('--', '__', '-_', '_-')):
        raise UsernameValidationError(
            'Your username cannot contain consecutive separators'
        )

    if normalized in RESERVED_USERNAMES:
        raise UsernameValidationError('That username is not available')

    return normalized
