from importlib.metadata import PackageNotFoundError, version

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import LoadingIndicator, Static

DEFAULT_SPLASH_TITLE = 'Ogham Chat\n᚛ᚑᚌᚆᚐᚋ᚜'


def _resolve_app_version() -> str:
    """Resolve installed package version, falling back to 'dev'."""
    try:
        return version('ogham-chat')
    except PackageNotFoundError:
        return r'\[dev]'


def _default_subtitle() -> str:
    return f'In-terminal relay chat client\nVersion {_resolve_app_version()}'


class SplashScreen(ModalScreen[None]):
    """Startup and about splash modal."""

    def __init__(
        self,
        title: str | None = None,
        subtitle: str | None = None,
        show_loader: bool = False,
    ) -> None:
        """Initialize splash content text."""
        super().__init__()
        self.splash_title_text = title if title is not None else DEFAULT_SPLASH_TITLE
        self.splash_subtitle_text = (
            subtitle if subtitle is not None else _default_subtitle()
        )
        self.show_loader = show_loader

    def compose(self) -> ComposeResult:
        """Render the splash card content."""
        with Vertical(id='splash-card'):
            yield Static(
                self.splash_title_text.strip(),
                id='splash-title',
                classes='splash-copy',
            )
            yield Static(
                self.splash_subtitle_text.strip(),
                id='splash-subtitle',
                classes='splash-copy',
            )
            if self.show_loader:
                yield LoadingIndicator(id='splash-loader')

    def on_click(self, event: events.Click) -> None:
        """Click to dismiss splash (only when loader is not shown)."""
        if self.show_loader:
            return
        del event
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        """Press any key to dismiss splash (only when loader is not shown)."""
        if self.show_loader:
            event.stop()
            return
        event.stop()
        self.dismiss(None)
