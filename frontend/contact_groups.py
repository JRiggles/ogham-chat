from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from frontend.local_prefs import LocalPreferences


class ContactGroupManager:
    """Manage contact-group membership and local persistence."""

    DEFAULT_PATH = Path.home() / '.ogham-chat' / 'oghamrc.json'

    def __init__(
        self,
        path: Path | None = None,
        prefs: LocalPreferences | None = None,
    ) -> None:
        """Initialize group manager with an optional storage path."""
        self.path = path or self.DEFAULT_PATH
        self.prefs = prefs or LocalPreferences(path=self.path)
        self._groups_by_user: dict[str, set[str]] = defaultdict(set)

    @property
    def groups_by_user(self) -> dict[str, set[str]]:
        """Return in-memory groups keyed by username."""
        return self._groups_by_user

    def contacts(self) -> set[str]:
        """Return all contacts that have a group record."""
        return set(self._groups_by_user)

    def ensure_contact(self, username: str) -> None:
        """Create an empty group record for a contact if missing."""
        normalized_username = username.strip()
        if not normalized_username:
            return
        self._groups_by_user.setdefault(normalized_username, set())

    def remove_contact(self, username: str) -> tuple[str, bool]:
        """Remove a contact and all its group memberships, then persist."""
        normalized_username = username.strip()
        if not normalized_username:
            return 'Usage: /contact remove <username>', False
        if normalized_username not in self._groups_by_user:
            return f'{normalized_username} is not a saved contact', False
        del self._groups_by_user[normalized_username]
        self._save()
        return f'Removed contact {normalized_username}', True

    def add_contact_group(
        self, username: str, group_name: str
    ) -> tuple[str, bool]:
        """Assign one contact to a named group and persist the update."""
        normalized_username = username.strip()
        normalized_group = self._normalize_group_name(group_name)
        if not normalized_username:
            return 'Usage: /group add <username> <group>', False
        if not normalized_group:
            return 'Group names cannot be empty', False
        if normalized_group in {'online', 'offline'}:
            return 'Group names cannot be online/offline', False

        self._groups_by_user.setdefault(normalized_username, set()).add(
            normalized_group
        )
        self._save()
        return f'Added {normalized_username} to group {normalized_group}', True

    def remove_contact_group(
        self, username: str, group_name: str
    ) -> tuple[str, bool]:
        """Remove one contact from a named group and persist the update."""
        normalized_username = username.strip()
        normalized_group = self._normalize_group_name(group_name)
        if not normalized_username:
            return 'Usage: /group remove <username> <group>', False
        if not normalized_group:
            return 'Group names cannot be empty', False

        groups = self._groups_by_user.get(normalized_username)
        if not groups or normalized_group not in groups:
            return (
                f'{normalized_username} is not in group {normalized_group}',
                False,
            )

        groups.remove(normalized_group)
        if not groups:
            self._groups_by_user[normalized_username] = set()
        self._save()
        return (
            f'Removed {normalized_username} from group {normalized_group}',
            True,
        )

    def move_contact_group(
        self,
        username: str,
        source_group: str,
        target_group: str,
    ) -> tuple[str, bool]:
        """Move one contact from source group to target group and persist."""
        normalized_username = username.strip()
        normalized_source = self._normalize_group_name(source_group)
        normalized_target = self._normalize_group_name(target_group)
        if not normalized_username:
            return (
                'Usage: /group move <username> <from_group> <to_group>',
                False,
            )
        if not normalized_source or not normalized_target:
            return 'Group names cannot be empty', False
        if normalized_target in {'online', 'offline'}:
            return 'Group names cannot be online/offline', False
        if normalized_source == normalized_target:
            return (
                f'{normalized_username} is already in group {normalized_target}',
                False,
            )

        groups = self._groups_by_user.get(normalized_username)
        if not groups or normalized_source not in groups:
            return (
                f'{normalized_username} is not in group {normalized_source}',
                False,
            )

        groups.remove(normalized_source)
        groups.add(normalized_target)
        self._save()
        return (
            f'Moved {normalized_username} from {normalized_source} '
            f'to {normalized_target}',
            True,
        )

    def delete_contact_group(self, group_name: str) -> tuple[str, bool]:
        """Delete one group assignment across all contacts and persist."""
        normalized_group = self._normalize_group_name(group_name)
        if not normalized_group:
            return 'Group names cannot be empty', False

        removed = 0
        for groups in self._groups_by_user.values():
            if normalized_group in groups:
                groups.remove(normalized_group)
                removed += 1

        if not removed:
            return f'Group {normalized_group} does not exist', False

        self._save()
        return (
            f'Deleted group {normalized_group} from {removed} contact(s)',
            True,
        )

    def list_contact_groups(self, username: str | None = None) -> str:
        """Return a text summary of configured groups for one/all contacts."""
        if username:
            normalized_username = username.strip()
            groups = sorted(
                self._groups_by_user.get(normalized_username, set())
            )
            if not groups:
                return f'{normalized_username}: (no groups)'
            return f'{normalized_username}: {", ".join(groups)}'

        groups_by_name: dict[str, list[str]] = defaultdict(list)
        for contact, groups in self._groups_by_user.items():
            for group in groups:
                groups_by_name[group].append(contact)

        if not groups_by_name:
            return 'No groups configured'

        lines = ['Groups:']
        for group in sorted(groups_by_name):
            contacts = ', '.join(sorted(groups_by_name[group]))
            lines.append(f'- {group}: {contacts}')
        return '\n'.join(lines)

    def load(self) -> None:
        """Load persisted contact groups from local JSON storage."""
        loaded = self.prefs.get_groups_by_user()
        normalized: dict[str, set[str]] = defaultdict(set)
        for username, groups in loaded.items():
            for group in groups:
                normalized_group = self._normalize_group_name(group)
                if normalized_group:
                    normalized[username].add(normalized_group)

        self._groups_by_user = normalized

    def _save(self) -> None:
        """Persist contact groups to local JSON storage."""
        self.prefs.set_groups_by_user(self._groups_by_user)

    def _normalize_group_name(self, group_name: str) -> str:
        """Normalize and validate group names for persistence and matching."""
        normalized = group_name.strip()
        if len(normalized) > 40:
            return ''
        return normalized
