from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from backend.core.username import validate_username


@dataclass(frozen=True)
class LocalIdentity:
    """One local identity persisted in the OS keychain."""

    account_id: str
    username: str
    created_at: str


@dataclass(frozen=True)
class IdentityRegistry:
    """Index of keychain-backed local identities."""

    account_ids: tuple[str, ...]
    active_account_id: str | None


class KeychainIdentityStore:
    """Persist and manage local identities in the OS keychain."""

    SERVICE_NAME = 'ogham-chat'
    REGISTRY_ACCOUNT_NAME = 'local-identities'
    ACCOUNT_NAME_PREFIX = 'local-identity:'

    def load_identity(self) -> LocalIdentity | None:
        """Load the active local identity from keychain, if present."""
        registry = self._load_registry()
        if registry.active_account_id is None:
            return None
        return self._load_account_identity(registry.active_account_id)

    def list_identities(self) -> list[LocalIdentity]:
        """Return all keychain-backed identities known on this device."""
        registry = self._load_registry()
        identities: list[LocalIdentity] = []
        valid_account_ids: list[str] = []

        for account_id in registry.account_ids:
            identity = self._load_account_identity(account_id)
            if identity is None:
                continue
            identities.append(identity)
            valid_account_ids.append(account_id)

        active_account_id = registry.active_account_id
        if active_account_id not in valid_account_ids:
            active_account_id = (
                valid_account_ids[0] if valid_account_ids else None
            )

        if (
            tuple(valid_account_ids) != registry.account_ids
            or active_account_id != registry.active_account_id
        ):
            self._save_registry(
                IdentityRegistry(
                    account_ids=tuple(valid_account_ids),
                    active_account_id=active_account_id,
                )
            )

        return identities

    def save_identity(
        self,
        username: str,
        *,
        created_at: str | None = None,
        make_active: bool = True,
    ) -> LocalIdentity:
        """Create and persist one keychain-backed local identity."""
        identity = LocalIdentity(
            account_id=uuid4().hex,
            username=validate_username(username),
            created_at=created_at or datetime.now(UTC).isoformat(),
        )
        self._save_account_identity(identity)

        registry = self._load_registry()
        account_ids = list(registry.account_ids)
        account_ids.append(identity.account_id)
        self._save_registry(
            IdentityRegistry(
                account_ids=tuple(account_ids),
                active_account_id=(
                    identity.account_id
                    if make_active
                    else registry.active_account_id
                ),
            )
        )

        return identity

    def set_active_identity(self, account_id: str) -> LocalIdentity:
        """Select one existing keychain-backed identity as active."""
        identity = self._load_account_identity(account_id)
        if identity is None:
            raise RuntimeError('Requested keychain identity does not exist')

        registry = self._load_registry()
        if account_id not in registry.account_ids:
            raise RuntimeError('Requested keychain identity does not exist')

        self._save_registry(
            IdentityRegistry(
                account_ids=registry.account_ids,
                active_account_id=account_id,
            )
        )
        return identity

    def delete_identity(self, account_id: str) -> None:
        """Delete one keychain-backed identity and update the active selection."""
        registry = self._load_registry()
        if account_id not in registry.account_ids:
            return

        self._delete_keychain_value(self._account_name(account_id))

        remaining_account_ids = tuple(
            current_id
            for current_id in registry.account_ids
            if current_id != account_id
        )
        next_active_account_id = registry.active_account_id
        if next_active_account_id == account_id:
            next_active_account_id = (
                remaining_account_ids[0] if remaining_account_ids else None
            )

        self._save_registry(
            IdentityRegistry(
                account_ids=remaining_account_ids,
                active_account_id=next_active_account_id,
            )
        )

    def _load_registry(self) -> IdentityRegistry:
        """Load the keychain identity registry, or an empty registry if absent."""
        payload = self._read_keychain_value(self.REGISTRY_ACCOUNT_NAME)
        if not payload:
            return IdentityRegistry(account_ids=(), active_account_id=None)

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                'Stored keychain identity registry is malformed'
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError(
                'Stored keychain identity registry is malformed'
            )

        account_ids = data.get('account_ids', [])
        active_account_id = data.get('active_account_id')

        if not isinstance(account_ids, list):
            raise RuntimeError(
                'Stored keychain identity registry is malformed'
            )

        normalized_account_ids: list[str] = []
        for account_id in account_ids:
            if isinstance(account_id, str) and account_id.strip():
                normalized_account_ids.append(account_id)

        if active_account_id is not None and not isinstance(
            active_account_id, str
        ):
            raise RuntimeError(
                'Stored keychain identity registry is malformed'
            )

        return IdentityRegistry(
            account_ids=tuple(normalized_account_ids),
            active_account_id=active_account_id,
        )

    def _save_registry(self, registry: IdentityRegistry) -> None:
        """Persist the keychain identity registry."""
        if not registry.account_ids:
            self._delete_keychain_value(self.REGISTRY_ACCOUNT_NAME)
            return

        payload = json.dumps(
            {
                'account_ids': list(registry.account_ids),
                'active_account_id': registry.active_account_id,
            },
            sort_keys=True,
        )
        self._write_keychain_value(self.REGISTRY_ACCOUNT_NAME, payload)

    def _load_account_identity(self, account_id: str) -> LocalIdentity | None:
        """Load one account-scoped identity from keychain."""
        payload = self._read_keychain_value(self._account_name(account_id))
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
        stored_account_id = data.get('account_id')
        if (
            not isinstance(username, str)
            or not isinstance(created_at, str)
            or not isinstance(stored_account_id, str)
        ):
            raise RuntimeError('Stored keychain identity is malformed')

        return LocalIdentity(
            account_id=stored_account_id,
            username=validate_username(username),
            created_at=created_at,
        )

    def _save_account_identity(self, identity: LocalIdentity) -> None:
        """Persist one account-scoped identity into keychain."""
        payload = json.dumps(asdict(identity), sort_keys=True)
        self._write_keychain_value(
            self._account_name(identity.account_id), payload
        )

    def _read_keychain_value(self, account_name: str) -> str | None:
        """Read one raw string value from keychain."""
        try:
            return keyring.get_password(self.SERVICE_NAME, account_name)
        except KeyringError as exc:
            raise RuntimeError(f'Keychain read failed: {exc}') from exc

    def _write_keychain_value(self, account_name: str, payload: str) -> None:
        """Persist one raw string value into keychain."""
        try:
            keyring.set_password(self.SERVICE_NAME, account_name, payload)
        except KeyringError as exc:
            raise RuntimeError(f'Keychain write failed: {exc}') from exc

    def _delete_keychain_value(self, account_name: str) -> None:
        """Delete one raw string value from keychain if present."""
        try:
            keyring.delete_password(self.SERVICE_NAME, account_name)
        except PasswordDeleteError:
            return
        except KeyringError as exc:
            raise RuntimeError(f'Keychain delete failed: {exc}') from exc

    def _account_name(self, account_id: str) -> str:
        """Build the keychain account name for one stored identity."""
        return f'{self.ACCOUNT_NAME_PREFIX}{account_id}'
