from __future__ import annotations

from collections.abc import Awaitable, Callable

from backend.core.config import ChatConfig
from backend.core.username import validate_username
from frontend.identity.store import KeychainIdentityStore, LocalIdentity


class IdentityResolutionCancelledError(RuntimeError):
    """Raised when startup identity resolution is cancelled by the user."""


class OnboardingCancelledError(IdentityResolutionCancelledError):
    """Raised when first-run onboarding is dismissed without a username."""


class AccountSelectionCancelledError(IdentityResolutionCancelledError):
    """Raised when the startup account switcher is dismissed."""


class IdentityManager:
    """Resolve and persist the local frontend identity for app startup."""

    def __init__(
        self,
        config: ChatConfig,
        identity_store: KeychainIdentityStore | None = None,
    ) -> None:
        self.config = config
        self.identity_store = identity_store or KeychainIdentityStore()

    async def resolve_username(
        self,
        prompt_for_username: Callable[[str | None], Awaitable[str | None]],
    ) -> str:
        """Resolve the runtime username from config, keychain, or onboarding."""
        if self.config.mode != 'relay':
            return self._commit_username(self.config.username or '')

        identity = self.identity_store.load_identity()
        if identity is not None:
            return self._commit_identity(identity)

        seed_username = self.config.requested_username
        chosen_username = await prompt_for_username(seed_username)
        if chosen_username is None:
            raise OnboardingCancelledError('Onboarding cancelled')

        identity = self.identity_store.save_identity(chosen_username)
        return self._commit_identity(identity)

    def get_active_identity(self) -> LocalIdentity | None:
        """Return the currently active local identity, if any."""
        return self.identity_store.load_identity()

    def get_local_identity(self, account_id: str) -> LocalIdentity | None:
        """Return one local identity by account id, if present."""
        return self._find_identity_by_account_id(account_id)

    def list_local_identities(self) -> list[LocalIdentity]:
        """Return all keychain-backed identities available on this device."""
        return self.identity_store.list_identities()

    def add_local_identity(
        self,
        username: str,
        *,
        make_active: bool = False,
    ) -> LocalIdentity:
        """Create one new local identity in keychain storage."""
        normalized_username = validate_username(username)
        if self._find_identity_by_username(normalized_username) is not None:
            raise RuntimeError(
                f'Local account already exists: {normalized_username}'
            )

        identity = self.identity_store.save_identity(
            normalized_username,
            make_active=make_active,
        )
        if make_active:
            self._commit_identity(identity)
        return identity

    def set_active_identity(self, account_id: str) -> str:
        """Switch the active local identity and return its username."""
        identity = self.identity_store.set_active_identity(account_id)
        return self._commit_identity(identity)

    def set_active_identity_by_username(self, username: str) -> str:
        """Switch the active local identity by username."""
        normalized_username = validate_username(username)
        identity = self._find_identity_by_username(normalized_username)
        if identity is None:
            raise RuntimeError(
                f'Local account not found: {normalized_username}'
            )
        return self.set_active_identity(identity.account_id)

    def delete_local_identity(self, account_id: str) -> str | None:
        """Delete one local identity and return the next active username, if any."""
        self.identity_store.delete_identity(account_id)
        next_identity = self.identity_store.load_identity()
        if next_identity is None:
            self.config.username = None
            return None
        return self._commit_identity(next_identity)

    def delete_local_identity_by_username(
        self, username: str
    ) -> tuple[str | None, bool]:
        """Delete one local identity by username.

        Returns the next active username, if any, plus whether the deleted
        account had been active.
        """
        normalized_username = validate_username(username)
        target_identity = self._find_identity_by_username(normalized_username)
        if target_identity is None:
            raise RuntimeError(
                f'Local account not found: {normalized_username}'
            )

        active_identity = self.get_active_identity()
        deleted_was_active = (
            active_identity is not None
            and active_identity.account_id == target_identity.account_id
        )
        next_username = self.delete_local_identity(target_identity.account_id)
        if not deleted_was_active and active_identity is not None:
            self._commit_identity(active_identity)
        return next_username, deleted_was_active

    def _commit_identity(self, identity: LocalIdentity) -> str:
        """Persist one resolved identity into runtime config only."""
        return self._commit_username(identity.username)

    def _commit_username(self, username: str) -> str:
        """Persist one resolved username into runtime config only."""
        self.config.username = username
        return username

    def _find_identity_by_username(
        self, username: str
    ) -> LocalIdentity | None:
        """Return the stored local identity matching one username."""
        for identity in self.list_local_identities():
            if identity.username == username:
                return identity
        return None

    def _find_identity_by_account_id(
        self, account_id: str
    ) -> LocalIdentity | None:
        """Return the stored local identity matching one account id."""
        for identity in self.list_local_identities():
            if identity.account_id == account_id:
                return identity
        return None
