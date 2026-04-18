from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from frontend.components.chat_log import ChatLog

WidgetT = TypeVar('WidgetT')

CANONICAL_SLASH_COMMANDS: tuple[str, ...] = (
    'help',
    'refresh',
    'clear',
    'chat',
    'status',
    'quit',
)

SLASH_COMMAND_ALIASES: dict[str, str] = {
    '?': 'help',
    'r': 'refresh',
    'c': 'clear',
    'cls': 'clear',
    'dm': 'chat',
    'peer': 'chat',
    's': 'status',
    'q': 'quit',
    'exit': 'quit',
}

ALL_SLASH_COMMANDS: tuple[str, ...] = tuple(
    sorted(set(CANONICAL_SLASH_COMMANDS) | set(SLASH_COMMAND_ALIASES))
)


@dataclass(frozen=True)
class SlashCommand:
    """Parsed slash command invocation."""

    name: str
    args: tuple[str, ...]


class SlashCommandHost(Protocol):
    """Capabilities required by the slash-command dispatcher."""

    active_peer: str | None
    known_contacts: set[str]
    online_users: set[str]
    seen_messages: set[Any]
    conversations: dict[str, list[Any]]

    def query_one(self, selector: str, expect_type: type[WidgetT]) -> WidgetT:
        """Return a widget by CSS selector and expected type."""
        ...

    def _set_status(self, text: str) -> None: ...

    def _write_system_message(self, text: str) -> None: ...

    def _set_active_peer(self, username: str) -> None: ...

    async def _load_conversation(self, peer_id: str) -> None: ...

    async def action_refresh(self) -> None:
        """Refresh chat history through the application's refresh action."""
        ...

    async def action_quit(self) -> None:
        """Close the application."""
        ...


HELP_TEXT = '\n'.join(
    [
        '__Slash commands:__',
        '**/help** (**/?**) - Show available commands',
        '**/refresh** (**/r**) - Refresh history now',
        '**/clear** (**/c**, **/cls**) - Clear current conversation from local view',
        '**/clear all** - Clear all local conversation history',
        '**/chat <username>** (**/dm**, **/peer**) - Switch active chat target',
        '**/status** (**/s**) - Show current chat status',
        '**/quit** (**/q**, **/exit**) - Quit app',
        '  (confirm with **/quit confirm|yes|y**)',
        '',
        '**//message** - Send text that starts with a slash',
        '',
        '**Esc** - Clear system messages like this one',
        '',
        '__Message formatting:__',
        r'\**bold\** - **Bold** text',
        r'\*italic\* - *Italic* text',
        r'\__underline\__ - __Underlined__ text',
        r'\~~strike\~~ - ~~Struck-through~~ text',
        r'\!highlight\! - Highlight important text',
        '',
        r'Escape formatting markers with "\"',
        r'\\*like this\\* → \*like this\*',
        r'\\* \\! \\__ \\~~ \\!',
        '',
    ]
)


def _write_system_output(host: SlashCommandHost, text: str) -> None:
    """Write slash-command output with a guaranteed trailing newline."""
    host._write_system_message(text if text.endswith('\n') else f'{text}\n')


def slash_command_completions(prefix: str) -> list[str]:
    """Return slash command candidates matching a partial command name."""
    normalized_prefix = prefix.strip().lower()
    return [
        command
        for command in ALL_SLASH_COMMANDS
        if command.startswith(normalized_prefix)
    ]


def parse_slash_command(text: str) -> SlashCommand | None:
    """Parse a slash command string into name and argument tokens."""
    stripped = text.strip()
    if not stripped.startswith('/') or stripped.startswith('//'):
        return None

    parts = stripped[1:].split()
    if not parts:
        return None

    name = parts[0].lower()
    args = tuple(parts[1:])
    return SlashCommand(name=name, args=args)


async def dispatch_slash_command(host: SlashCommandHost, text: str) -> bool:
    """Execute one slash command and return whether input was handled."""
    command = parse_slash_command(text)
    if command is None:
        return False

    canonical_name = SLASH_COMMAND_ALIASES.get(command.name, command.name)

    if canonical_name == 'help':
        _write_system_output(host, HELP_TEXT)
        host._set_status('Slash command help')
        return True

    if canonical_name == 'refresh':
        await host.action_refresh()
        return True

    if canonical_name == 'clear':
        if command.args and command.args[0].lower() == 'all':
            host.conversations.clear()
            host.seen_messages.clear()
            chat = host.query_one('#chat', ChatLog)
            chat.set_messages([])
            _write_system_output(
                host, 'Cleared all local conversation history'
            )
            host._set_status('Cleared local history')
            return True

        if not host.active_peer:
            host._set_status('No active conversation to clear')
            return True

        host.conversations[host.active_peer] = []
        chat = host.query_one('#chat', ChatLog)
        chat.set_messages([])
        _write_system_output(
            host, f'Cleared local conversation with {host.active_peer}'
        )
        host._set_status(f'Cleared local conversation with {host.active_peer}')
        return True

    if canonical_name == 'chat':
        if not command.args:
            host._set_status('Usage: /chat <username>')
            return True

        username = command.args[0].strip()
        if not username:
            host._set_status('Usage: /chat <username>')
            return True

        host._set_active_peer(username)
        await host._load_conversation(username)
        host._set_status(f'Now chatting with {username}')
        return True

    if canonical_name == 'status':
        current_chat = host.active_peer or '(none)'
        _write_system_output(
            host,
            'Status:\n'
            f'- Current chat: {current_chat}\n'
            f'- Known contacts: {len(host.known_contacts)}\n'
            f'- Online users: {len(host.online_users)}',
        )
        host._set_status('Displayed chat status')
        return True

    if canonical_name == 'quit':
        confirmed = bool(command.args) and command.args[0].lower() in {
            'confirm',
            'yes',
            'y',
        }
        if not confirmed:
            _write_system_output(
                host, 'Confirm quit with /quit confirm (aliases: /q, /exit)'
            )
            host._set_status('Quit requires confirmation: /quit confirm|yes|y')
            return True

        await host.action_quit()
        return True

    host._set_status(f'Unknown slash command: /{command.name} (try /help)')
    return True
