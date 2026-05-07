from __future__ import annotations

from collections.abc import Awaitable, Callable

from backend.core.config import ChatConfig
from frontend.identity.store import KeychainIdentityStore
from frontend.local_prefs import LocalPreferences


class OnboardingCancelledError(RuntimeError):
    """Raised when first-run onboarding is dismissed without a username."""


class IdentityManager:
    """Resolve and persist the local frontend identity for app startup."""

    def __init__(
        self,
        config: ChatConfig,
        local_prefs: LocalPreferences,
        identity_store: KeychainIdentityStore | None = None,
    ) -> None:
        self.config = config
        self.local_prefs = local_prefs
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
            return self._commit_username(identity.username)

        seed_username = (
            self.config.requested_username
            or self.local_prefs.get_last_known_username()
        )
        chosen_username = await prompt_for_username(seed_username)
        if chosen_username is None:
            raise OnboardingCancelledError('Onboarding cancelled')

        identity = self.identity_store.save_identity(chosen_username)
        return self._commit_username(identity.username)

    def _commit_username(self, username: str) -> str:
        """Persist one resolved username into config and local prefs."""
        self.config.username = username
        if self.config.mode == 'relay' and username:
            self.local_prefs.set_last_known_username(username)
            self.local_prefs.set_onboarding_completed(True)
        return username
