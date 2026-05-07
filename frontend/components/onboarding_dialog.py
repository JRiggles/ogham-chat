from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from backend.core.username import (
    USERNAME_RULES_SUMMARY,
    UsernameValidationError,
    username_requirements_text,
    validate_username,
)


class OnboardingScreen(ModalScreen[str | None]):
    """Interactive first-run onboarding for creating a local identity."""

    def __init__(self, seed_username: str | None = None) -> None:
        """Initialize onboarding with an optional seed username."""
        super().__init__()
        self.seed_username = seed_username or ''

    def compose(self) -> ComposeResult:
        """Render username onboarding content."""
        with Vertical(id='onboarding-card'):
            yield Static(
                "Welcome to Ogham Chat, let's get started!",
                id='onboarding-title',
            )
            yield Static(
                'No existing Ogham Chat identity was found. Choose a username '
                'to create one before connecting to the relay.',
                id='onboarding-subtitle',
                classes='onboarding-copy',
            )
            yield Static(
                USERNAME_RULES_SUMMARY,
                id='onboarding-rules-summary',
                classes='onboarding-copy',
            )
            yield Static(
                username_requirements_text(),
                id='onboarding-rules',
                classes='onboarding-copy',
            )
            yield Input(
                value=self.seed_username,
                placeholder='username',
                id='onboarding-username',
            )
            yield Static('', id='onboarding-error')
            with Horizontal(id='onboarding-actions'):
                yield Button(
                    'Continue', variant='primary', id='onboarding-submit'
                )
                yield Button('Quit', variant='default', id='onboarding-cancel')

    def on_mount(self) -> None:
        """Focus the username input on mount."""
        self.query_one('#onboarding-username', Input).focus()

    @on(Input.Submitted, '#onboarding-username')
    def _on_input_submitted(self) -> None:
        """Submit onboarding when Enter is pressed in the username field."""
        self._submit()

    @on(Button.Pressed, '#onboarding-submit')
    def _on_submit_pressed(self) -> None:
        """Submit onboarding when the primary action is pressed."""
        self._submit()

    @on(Button.Pressed, '#onboarding-cancel')
    def _on_cancel_pressed(self) -> None:
        """Dismiss onboarding without creating an identity."""
        self.dismiss(None)

    def _submit(self) -> None:
        """Validate current input and dismiss with the chosen username."""
        input_widget = self.query_one('#onboarding-username', Input)
        error_widget = self.query_one('#onboarding-error', Static)

        try:
            username = validate_username(input_widget.value)
        except UsernameValidationError as exc:
            error_widget.update(str(exc))
            return

        error_widget.update('')
        self.dismiss(username)
