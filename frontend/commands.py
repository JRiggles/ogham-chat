from collections.abc import Callable

from frontend.contact_groups import ContactGroupManager


class ContactGroupCommandActions:
    """Bridge slash commands to contact-group manager side effects."""

    def __init__(
        self,
        manager: ContactGroupManager,
        on_groups_changed: Callable[[], None],
    ) -> None:
        """Store dependencies for group command execution."""
        self.manager = manager
        self.on_groups_changed = on_groups_changed

    def add_contact_group(self, username: str, group_name: str) -> str:
        """Assign one contact to a named group and trigger refresh."""
        result, changed = self.manager.add_contact_group(username, group_name)
        if changed:
            self.on_groups_changed()
        return result

    def remove_contact_group(self, username: str, group_name: str) -> str:
        """Remove one contact from a named group and trigger refresh."""
        result, changed = self.manager.remove_contact_group(
            username,
            group_name,
        )
        if changed:
            self.on_groups_changed()
        return result

    def move_contact_group(
        self,
        username: str,
        source_group: str,
        target_group: str,
    ) -> str:
        """Move one contact between groups and trigger refresh."""
        result, changed = self.manager.move_contact_group(
            username,
            source_group,
            target_group,
        )
        if changed:
            self.on_groups_changed()
        return result

    def delete_contact_group(self, group_name: str) -> str:
        """Delete one group and trigger refresh."""
        result, changed = self.manager.delete_contact_group(group_name)
        if changed:
            self.on_groups_changed()
        return result

    def list_contact_groups(self, username: str | None = None) -> str:
        """Return a text summary of configured groups."""
        return self.manager.list_contact_groups(username)


class ContactCommandActions:
    """Bridge slash commands to contact manager side effects."""

    def __init__(
        self,
        manager: ContactGroupManager,
        on_contacts_changed: Callable[[], None],
    ) -> None:
        """Store dependencies for contact command execution."""
        self.manager = manager
        self.on_contacts_changed = on_contacts_changed

    def add_contact(self, username: str) -> str:
        """Add a contact and trigger refresh."""
        # TODO: validate username against the DB — add if exists, notify if not
        normalized = username.strip()
        if not normalized:
            return 'Usage: /contact add <username>'
        if normalized in self.manager.contacts():
            return f'{normalized} is already a contact'
        self.manager.ensure_contact(normalized)
        self.manager._save()
        self.on_contacts_changed()
        return f'Added contact {normalized}'

    def remove_contact(self, username: str) -> str:
        """Remove a contact and trigger refresh."""
        result, changed = self.manager.remove_contact(username)
        if changed:
            self.on_contacts_changed()
        return result


from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from frontend.components.chat_log import ChatLog

WidgetT = TypeVar('WidgetT')

CANONICAL_SLASH_COMMANDS: tuple[str, ...] = (
    'help',
    'refresh',
    'clear',
    'chat',
    'contact',
    'group',
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
    'g': 'group',
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


class ContactActions(Protocol):
    """Operations available for the /contact command namespace."""

    def add_contact(self, username: str) -> str:
        """Add a contact and return status text."""
        ...

    def remove_contact(self, username: str) -> str:
        """Remove a contact and return status text."""
        ...


class GroupCommandActions(Protocol):
    """Operations available for the /group command namespace."""

    def add_contact_group(self, username: str, group_name: str) -> str:
        """Assign one contact to a named group and return status text."""
        ...

    def remove_contact_group(self, username: str, group_name: str) -> str:
        """Remove one contact from a named group and return status text."""
        ...

    def move_contact_group(
        self,
        username: str,
        source_group: str,
        target_group: str,
    ) -> str:
        """Move one contact from source group to target group."""
        ...

    def delete_contact_group(self, group_name: str) -> str:
        """Delete a group across contacts and return status text."""
        ...

    def list_contact_groups(self, username: str | None = None) -> str:
        """Return a human-readable summary of contact groups."""
        ...


class SlashCommandHost(Protocol):
    """Capabilities required by the slash-command dispatcher."""

    active_peer: str | None
    known_contacts: set[str]
    online_users: set[str]
    seen_messages: set[Any]
    conversations: dict[str, list[Any]]
    contact_commands: ContactActions
    group_commands: GroupCommandActions

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
        '**/contact** - Manage contacts',
        '  /contact add <username>',
        '  /contact remove <username>',
        '**/group** (**/g**) - Manage contact groups',
        '  /group add <username> <group>',
        '  /group remove <group> - remove entire group',
        '  /group remove <username> <group> - remove user from group',
        '  /group move <username> <from group> <to group>',
        '  /group delete <group>',
        '  /group list [username]',
        '**/status** (**/s**) - Show current chat status',
        '**/quit** (**/q**, **/exit**) - Quit app (requires confirmation)',
        '  /quit confirm|yes|y',
        '',
        '**//message** - Send text that starts with a slash',
        '',
        '**Esc** - Clear system messages like this one',
        '',
        '__Message formatting:__',
        r'\**bold\** - **Bold** text',
        r'\*italic\* - *Italic* text',
        r'\__underline\__ - __Underlined__ text',
        r'\~~strike\~~ - ~~Strikethrough~~ text',
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

    if canonical_name == 'contact':
        if not command.args:
            host._set_status('Usage: /contact add|remove <username>')
            return True

        action = command.args[0].lower()
        args = command.args[1:]

        if action == 'add':
            if not args:
                host._set_status('Usage: /contact add <username>')
                return True
            username = args[0]
            result = host.contact_commands.add_contact(username)
            _write_system_output(host, result)
            host._set_status(result)
            return True

        if action == 'remove':
            if not args:
                host._set_status('Usage: /contact remove <username>')
                return True
            username = args[0]
            result = host.contact_commands.remove_contact(username)
            _write_system_output(host, result)
            host._set_status(result)
            return True

        host._set_status('Usage: /contact add|remove <username>')
        return True

    if canonical_name == 'group':
        if not command.args:
            host._set_status('Usage: /group add|remove|delete|list ...')
            return True

        action = command.args[0].lower()
        args = command.args[1:]

        if action == 'add':
            if len(args) < 2:
                host._set_status('Usage: /group add <username> <group>')
                return True
            username = args[0]
            group = ' '.join(args[1:])
            result = host.group_commands.add_contact_group(username, group)
            _write_system_output(host, result)
            host._set_status(result)
            return True

        if action == 'remove':
            if not args:
                host._set_status(
                    'Usage: /group remove <group> or '
                    '/group remove <username> <group>'
                )
                return True
            if len(args) == 1:
                group = args[0]
                result = host.group_commands.delete_contact_group(group)
            else:
                username = args[0]
                group = ' '.join(args[1:])
                result = host.group_commands.remove_contact_group(
                    username,
                    group,
                )
            _write_system_output(host, result)
            host._set_status(result)
            return True

        if action == 'move':
            if len(args) < 3:
                host._set_status(
                    'Usage: /group move <username> <from_group> <to_group>'
                )
                return True
            username = args[0]
            source_group = args[1]
            target_group = ' '.join(args[2:])
            result = host.group_commands.move_contact_group(
                username,
                source_group,
                target_group,
            )
            _write_system_output(host, result)
            host._set_status(result)
            return True

        if action == 'delete':
            if not args:
                host._set_status('Usage: /group delete <group>')
                return True
            group = ' '.join(args)
            result = host.group_commands.delete_contact_group(group)
            _write_system_output(host, result)
            host._set_status(result)
            return True

        if action == 'list':
            username = args[0] if args else None
            result = host.group_commands.list_contact_groups(username)
            _write_system_output(host, result)
            host._set_status('Displayed groups')
            return True

        host._set_status('Usage: /group add|remove|move|delete|list ...')
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
