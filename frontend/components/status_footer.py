from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Footer, Static


class StatusFooter(Footer):
    """Footer that combines key bindings with app status text."""

    status_text = reactive('')

    def compose(self) -> ComposeResult:
        """Compose footer bindings plus the current status label."""
        yield from super().compose()
        yield Static(self.status_text, id='status-message')

    def _update_status_label(self, text: str) -> bool:
        """Update mounted status label text if available.

        Returns:
            True when the status label exists and was updated.
        """
        try:
            label = self.query_one('#status-message', Static)
        except NoMatches:
            return False

        label.update(text)
        self.refresh()
        return True

    def watch_status_text(self, text: str) -> None:
        """Apply reactive status changes to the mounted status label."""
        self._update_status_label(text)

    def on_mount(self) -> None:
        """Ensure the label reflects the latest status after mounting."""
        super().on_mount()
        self._update_status_label(self.status_text)

    def set_status(self, text: str) -> None:
        """Update footer status text."""
        self.status_text = text
        # Also push directly so status updates remain reliable during recomposes.
        self._update_status_label(text)
