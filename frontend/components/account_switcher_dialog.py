from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, RadioButton, RadioSet, Static

from frontend.identity import LocalIdentity


@dataclass(frozen=True)
class StartupAccountChoice:
    """One startup account selection result returned by the chooser."""

    account_id: str
    make_default: bool
    hide_dialog: bool


class AccountSwitcherScreen(ModalScreen[StartupAccountChoice | None]):
    """Prompt for a startup account when multiple local identities exist."""

    def __init__(
        self,
        identities: list[LocalIdentity],
        *,
        selected_account_id: str | None = None,
        default_account_id: str | None = None,
        hide_dialog: bool = False,
        title: str = 'Choose a startup account',
        subtitle: str = (
            'Multiple Ogham Chat identities were found on this device. '
            'Select one to use for this session:'
        ),
        submit_label: str = 'Continue',
        cancel_label: str = 'Quit',
        show_preferences: bool = True,
    ) -> None:
        """Initialize chooser state from the available local identities."""
        super().__init__()
        self.identities = sorted(
            identities,
            key=lambda identity: identity.username.lower(),
        )
        self.selected_account_id = self._resolve_selected_account_id(
            selected_account_id
        )
        self.make_default = default_account_id == self.selected_account_id
        self.hide_dialog = hide_dialog
        self.dialog_title = title
        self.dialog_subtitle = subtitle
        self.submit_label = submit_label
        self.cancel_label = cancel_label
        self.show_preferences = show_preferences

    def compose(self) -> ComposeResult:
        """Render startup account selection content."""
        with Vertical(id='account-switcher-card'):
            yield Static(
                self.dialog_title,
                id='account-switcher-title',
            )

            yield Static(
                self.dialog_subtitle,
                id='account-switcher-subtitle',
                classes='account-switcher-copy',
            )
            yield Static('', id='account-switcher-error')
            with Vertical(id='account-switcher-options'):
                yield RadioSet(
                    *[
                        RadioButton(
                            identity.username,
                            value=(
                                identity.account_id == self.selected_account_id
                            ),
                        )
                        for identity in self.identities
                    ],
                    id='account-switcher-radio-set',
                )
            if self.show_preferences:
                with Vertical(id='account-switcher-preferences'):
                    yield Checkbox(
                        'Use the selected account by default on startup',
                        value=self.make_default,
                        id='account-switcher-default-toggle',
                    )
                    yield Checkbox(
                        "Don't show this account chooser again on startup",
                        value=self.hide_dialog,
                        id='account-switcher-hide-toggle',
                    )
            with Horizontal(id='account-switcher-actions'):
                yield Button(
                    self.submit_label,
                    variant='primary',
                    id='account-switcher-submit',
                )
                yield Button(
                    self.cancel_label,
                    variant='default',
                    id='account-switcher-cancel',
                )

    def on_mount(self) -> None:
        """Focus the account radio set when the chooser mounts."""
        self.query_one('#account-switcher-radio-set', RadioSet).focus()

    @on(RadioSet.Changed, '#account-switcher-radio-set')
    def _on_account_changed(self, event: RadioSet.Changed) -> None:
        """Track the currently selected account from the radio set."""
        self.selected_account_id = self.identities[event.index].account_id
        self.query_one('#account-switcher-error', Static).update('')

    @on(Checkbox.Changed, '#account-switcher-default-toggle')
    def _on_default_changed(self, event: Checkbox.Changed) -> None:
        """Track whether the chosen account should become the startup default."""
        self.make_default = event.checkbox.value

    @on(Checkbox.Changed, '#account-switcher-hide-toggle')
    def _on_hide_changed(self, event: Checkbox.Changed) -> None:
        """Track whether the chooser should be hidden on future startups."""
        self.hide_dialog = event.checkbox.value

    @on(Button.Pressed)
    def _on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle dialog action buttons."""
        button_id = event.button.id or ''

        if button_id == 'account-switcher-submit':
            self._submit()
            return

        if button_id == 'account-switcher-cancel':
            self.dismiss(None)

    def _submit(self) -> None:
        """Dismiss the chooser with one concrete startup account choice."""
        if not self.selected_account_id:
            self.query_one('#account-switcher-error', Static).update(
                'Choose an account before continuing.'
            )
            return

        self.query_one('#account-switcher-error', Static).update('')
        self.dismiss(
            StartupAccountChoice(
                account_id=self.selected_account_id,
                make_default=self.make_default,
                hide_dialog=self.hide_dialog,
            )
        )

    def _resolve_selected_account_id(
        self, selected_account_id: str | None
    ) -> str:
        """Pick a valid initial selected account id for the chooser."""
        account_ids = {identity.account_id for identity in self.identities}
        if selected_account_id in account_ids:
            return selected_account_id
        return self.identities[0].account_id
