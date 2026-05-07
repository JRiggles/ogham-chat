from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from backend.core.username import validate_username


@dataclass(frozen=True)
class LocalIdentity:
    """Minimal local identity metadata stored in the system keychain."""

    username: str
    created_at: str


class KeychainIdentityStore:
    """Persist and retrieve the local relay identity from the OS keychain."""

    SERVICE_NAME = 'ogham-chat'
    ACCOUNT_NAME = 'local-identity'

    def load_identity(self) -> LocalIdentity | None:
        """Load the current local identity from keychain, if present."""
        try:
            payload = keyring.get_password(
                self.SERVICE_NAME, self.ACCOUNT_NAME
            )
        except KeyringError as exc:
            raise RuntimeError(f'Keychain read failed: {exc}') from exc

        if not payload:
            return None

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                'Stored keychain identity is malformed'
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError('Stored keychain identity is malformed')

        username = data.get('username')
        created_at = data.get('created_at')
        if not isinstance(username, str) or not isinstance(created_at, str):
            raise RuntimeError('Stored keychain identity is malformed')

        return LocalIdentity(
            username=validate_username(username),
            created_at=created_at,
        )

    def save_identity(self, username: str) -> LocalIdentity:
        """Persist one local identity into the keychain and return it."""
        identity = LocalIdentity(
            username=validate_username(username),
            created_at=datetime.now(UTC).isoformat(),
        )
        payload = json.dumps(asdict(identity), sort_keys=True)

        try:
            keyring.set_password(self.SERVICE_NAME, self.ACCOUNT_NAME, payload)
        except KeyringError as exc:
            raise RuntimeError(f'Keychain write failed: {exc}') from exc

        return identity

    def delete_identity(self) -> None:
        """Remove the local identity from the keychain if present."""
        try:
            keyring.delete_password(self.SERVICE_NAME, self.ACCOUNT_NAME)
        except PasswordDeleteError:
            return
        except KeyringError as exc:
            raise RuntimeError(f'Keychain delete failed: {exc}') from exc
