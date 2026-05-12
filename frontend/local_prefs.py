from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


class LocalPreferences:
    """Persist non-sensitive app preferences in a local JSON config."""

    DEFAULT_PATH = Path.home() / '.ogham-chat' / '.oghamrc'
    LATEST_SEEN_MESSAGES_KEY = 'latest_seen_message_by_account'

    def __init__(self, path: Path | None = None) -> None:
        """Initialize local preferences storage."""
        self.path = path or self.DEFAULT_PATH
        self._data: dict[str, object] = {'version': 1}
        self.load()

    def load(self) -> None:
        """Load preferences from disk."""
        payload = self._read_json_file(self.path)
        if isinstance(payload, dict):
            self._data = payload
        else:
            self._data = {'version': 1}

        if not isinstance(self._data.get('version'), int):
            self._data['version'] = 1

    def save(self) -> None:
        """Persist current preferences to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )

    def get_theme(self) -> str | None:
        """Return persisted theme name, if any."""
        theme = self._data.get('theme')
        if isinstance(theme, str) and theme.strip():
            return theme.strip()
        return None

    def set_theme(self, theme_name: str) -> None:
        """Persist selected theme name."""
        self._data['theme'] = theme_name.strip()
        self.save()

    def get_startup_default_account_id(self) -> str | None:
        """Return the preferred startup account id, if one is set."""
        account_id = self._data.get('startup_default_account_id')
        if isinstance(account_id, str) and account_id.strip():
            return account_id.strip()
        return None

    def set_startup_default_account_id(self, account_id: str | None) -> None:
        """Persist or clear the preferred startup account id."""
        if account_id is None:
            self._data.pop('startup_default_account_id', None)
        else:
            self._data['startup_default_account_id'] = account_id.strip()
        self.save()

    def get_hide_startup_account_switcher(self) -> bool:
        """Return whether the startup account chooser should stay hidden."""
        return bool(self._data.get('hide_startup_account_switcher', False))

    def set_hide_startup_account_switcher(self, hidden: bool) -> None:
        """Persist whether the startup account chooser should stay hidden."""
        self._data['hide_startup_account_switcher'] = bool(hidden)
        self.save()

    def get_groups_by_user(self) -> dict[str, set[str]]:
        """Return persisted contact groups as username -> set[group]."""
        groups_payload = self._data.get('groups_by_user', {})
        if not isinstance(groups_payload, dict):
            return defaultdict(set)

        loaded: dict[str, set[str]] = defaultdict(set)
        for username, groups in groups_payload.items():
            if not isinstance(username, str) or not isinstance(groups, list):
                continue
            for group in groups:
                if isinstance(group, str) and group.strip():
                    loaded[username].add(group.strip())

        return loaded

    def set_groups_by_user(self, groups_by_user: dict[str, set[str]]) -> None:
        """Persist contact groups from username -> set[group]."""
        self._data['groups_by_user'] = {
            username: sorted(groups)
            for username, groups in sorted(groups_by_user.items())
            if groups
        }
        self.save()

    def get_latest_seen_message_at(
        self,
        account_username: str,
        peer_username: str,
    ) -> datetime | None:
        """Return the newest persisted seen-message timestamp for one peer."""
        account_key = account_username.strip()
        peer_key = peer_username.strip()
        if not account_key or not peer_key:
            return None

        payload = self._data.get(self.LATEST_SEEN_MESSAGES_KEY, {})
        if not isinstance(payload, dict):
            return None

        account_payload = payload.get(account_key)
        if not isinstance(account_payload, dict):
            return None

        seen_at = account_payload.get(peer_key)
        if not isinstance(seen_at, str) or not seen_at.strip():
            return None

        return self._parse_datetime(seen_at.strip())

    def set_latest_seen_message_at(
        self,
        account_username: str,
        peer_username: str,
        seen_at: datetime | None,
    ) -> None:
        """Persist or clear the newest seen-message timestamp for one peer."""
        account_key = account_username.strip()
        peer_key = peer_username.strip()
        if not account_key or not peer_key:
            return

        payload = self._data.get(self.LATEST_SEEN_MESSAGES_KEY)
        if not isinstance(payload, dict):
            payload = {}
            self._data[self.LATEST_SEEN_MESSAGES_KEY] = payload

        if seen_at is None:
            account_payload = payload.get(account_key)
            if isinstance(account_payload, dict):
                account_payload.pop(peer_key, None)
                if not account_payload:
                    payload.pop(account_key, None)
            if not payload:
                self._data.pop(self.LATEST_SEEN_MESSAGES_KEY, None)
            self.save()
            return

        account_payload = payload.get(account_key)
        if not isinstance(account_payload, dict):
            account_payload = {}
            payload[account_key] = account_payload

        account_payload[peer_key] = seen_at.isoformat()
        self.save()

    @staticmethod
    def _parse_datetime(raw_value: str) -> datetime | None:
        """Parse one persisted ISO datetime string, returning None on error."""
        try:
            return datetime.fromisoformat(raw_value)
        except ValueError:
            return None

    @staticmethod
    def _read_json_file(path: Path) -> object | None:
        """Read and parse one JSON file; return None on any file/parse error."""
        try:
            raw = path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return None
        except OSError:
            return None

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
