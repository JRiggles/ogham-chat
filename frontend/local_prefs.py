from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from backend.core.username import validate_username


class LocalPreferences:
    """Persist non-sensitive app preferences in a local JSON config."""

    DEFAULT_PATH = Path.home() / '.ogham-chat' / '.oghamrc'

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

    def get_onboarding_completed(self) -> bool:
        """Return whether first-run onboarding has completed."""
        completed = self._data.get('onboarding_completed')
        return bool(completed)

    def set_onboarding_completed(self, completed: bool) -> None:
        """Persist first-run onboarding completion state."""
        self._data['onboarding_completed'] = bool(completed)
        self.save()

    def get_last_known_username(self) -> str | None:
        """Return the last stored local username, if any."""
        username = self._data.get('last_known_username')
        if not isinstance(username, str):
            return None
        try:
            return validate_username(username)
        except ValueError:
            return None

    def set_last_known_username(self, username: str | None) -> None:
        """Persist the last resolved local username."""
        if username is None:
            self._data.pop('last_known_username', None)
        else:
            self._data['last_known_username'] = validate_username(username)
        self.save()

    def clear_onboarding_state(self) -> None:
        """Remove persisted onboarding metadata from local preferences."""
        self._data.pop('onboarding_completed', None)
        self._data.pop('last_known_username', None)
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
