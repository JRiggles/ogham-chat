from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Footer, Static


class StatusFooter(Footer):
    """Footer that combines key bindings with app status text."""

    DEFAULT_CSS = """
    #status-message {
        color: $foreground;
    }
    """

    status_text = reactive('')

    def compose(self) -> ComposeResult:
        """Compose footer bindings plus the current status label."""
        yield from super().compose()
        yield Static(self.status_text, id='status-message')

    def _update_status_label(self, text: str, color: str | None = None) -> bool:
        """Update mounted status label text if available.

        Returns:
            True when the status label exists and was updated.
        """
        try:
            label = self.query_one('#status-message', Static)
        except NoMatches:
            return False

        label.update(text)
        if color is not None:
            # resolve $variable references (e.g. '$warning') from theme
            if color.startswith('$'):
                resolved = self.app.get_css_variables().get(color[1:])
                label.styles.color = resolved if resolved else None
            else:
                label.styles.color = color
        else:
            label.styles.color = None  # reset to DEFAULT_CSS ($foreground)
        self.refresh()
        return True

    def watch_status_text(self, text: str) -> None:
        """Apply reactive status changes to the mounted status label."""
        self._update_status_label(text)

    def on_mount(self) -> None:
        """Ensure the label reflects the latest status after mounting."""
        super().on_mount()
        self._update_status_label(self.status_text)

    def set_status(self, text: str, color: str | None = None) -> None:
        """Update footer status text with an optional foreground color."""
        self.status_text = text
        self._update_status_label(text, color)
