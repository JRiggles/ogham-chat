import re
import textwrap
from datetime import UTC, datetime

from rich.console import Console
from rich.markup import escape
from rich.text import Text
from textual.widgets import RichLog

from backend.core.message import ChatMessage


class ChatMessageRenderer:
    """Render chat messages into styled Rich text lines for the chat log."""

    ESCAPABLE_MARKERS: tuple[str, ...] = ('**', '__', '~~', '*', '!')

    INLINE_STYLES: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r'\*\*(.+?)\*\*', re.DOTALL), 'bold'),
        (re.compile(r'__(.+?)__', re.DOTALL), 'underline'),
        (re.compile(r'~~(.+?)~~', re.DOTALL), 'strike'),
        (
            re.compile(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', re.DOTALL),
            'italic',
        ),
    )
    HIGHLIGHT_PATTERN = re.compile(r'(?<!\!)!([^!\n]+?)!(?!\!)', re.DOTALL)

    def __init__(
        self,
        self_style: str = 'green',
        peer_style: str = 'blue',
        foreground: str = 'white',
    ) -> None:
        """Configure styles for local-user and peer message rendering."""
        self.self_style = self_style
        self.peer_style = peer_style
        self.foreground = foreground

    def render(
        self,
        message: ChatMessage,
        width: int,
        self_username: str,
        console: Console,
    ) -> list[Text]:
        """Render one chat message into display-ready Rich text lines."""
        if message.is_system:
            return self._render_system_message(message, width, console)

        is_self = message.sender == self_username
        line_style = self.self_style if is_self else self.peer_style
        header_style = f'bold {self.foreground} on {line_style}'
        name_style = f'bold {self.foreground} on {line_style}'
        body_width = max(width, 1)

        rendered_lines: list[Text] = []

        created_at_local = self._to_local_time(message.created_at)

        header = (
            f' {message.sender} - {created_at_local.strftime("%H:%M:%S")} '
        )
        rendered_header = Text(header, style=header_style)
        name_start = rendered_header.plain.find(message.sender)
        if name_start != -1:
            rendered_header.stylize(
                name_style,
                name_start,
                name_start + len(message.sender),
            )
        rendered_lines.append(rendered_header)

        rendered_lines.extend(
            self._render_formatted_lines(
                message.content,
                body_width,
                line_style,
                console,
                highlight_style=f'bold {self.foreground} on {line_style}',
            )
        )

        rendered_lines.append(Text(''))

        return rendered_lines

    def _render_system_message(
        self, message: ChatMessage, width: int, console: Console
    ) -> list[Text]:
        """Render one system message with dimmed styling."""
        return self._render_formatted_lines(
            message.content,
            max(width, 1),
            'dim',
            console,
            highlight_style='bold',
        )

    def _render_formatted_lines(
        self,
        content: str,
        width: int,
        base_style: str,
        console: Console,
        highlight_style: str,
    ) -> list[Text]:
        """Render wrapped text lines while preserving inline formatting spans."""
        rendered_lines: list[Text] = []
        for raw_line in content.split('\n'):
            formatted = self._render_inline_markup(
                raw_line,
                base_style,
                highlight_style,
            )
            rendered_lines.extend(
                formatted.wrap(console, max(width, 1))
                or [Text('', style=base_style)]
            )
        return rendered_lines

    def _render_inline_markup(
        self,
        text: str,
        base_style: str,
        highlight_style: str,
    ) -> Text:
        """Parse a small markdown-like inline syntax into Rich text spans."""
        protected_text, replacements = self._protect_escaped_markers(text)
        markup = escape(protected_text)
        for pattern, rich_style in self.INLINE_STYLES:
            markup = pattern.sub(rf'[{rich_style}]\1[/]', markup)
        markup = self.HIGHLIGHT_PATTERN.sub(
            lambda match: f'[{highlight_style}]{match.group(1)}[/]',
            markup,
        )
        for token, marker in replacements.items():
            markup = markup.replace(token, marker)
        return Text.from_markup(markup, style=base_style)

    @classmethod
    def _protect_escaped_markers(cls, text: str) -> tuple[str, dict[str, str]]:
        """Replace escaped formatting markers with placeholders.

        This preserves literal marker text through subsequent regex parsing.
        """
        replacements: dict[str, str] = {}
        protected = text
        for index, marker in enumerate(cls.ESCAPABLE_MARKERS):
            token = f'\x00ESCAPED_MARKER_{index}\x00'
            protected = protected.replace(f'\\{marker}', token)
            replacements[token] = marker
        return protected, replacements

    def _wrap_preserving_newlines(self, text: str, width: int) -> list[str]:
        """Wrap text to width while preserving explicit newline boundaries."""
        wrapped_lines: list[str] = []
        for raw_line in text.split('\n'):
            wrapped_lines.extend(
                textwrap.wrap(
                    raw_line,
                    width=width,
                    replace_whitespace=False,
                    drop_whitespace=False,
                    break_long_words=True,
                    break_on_hyphens=False,
                )
                or ['']
            )
        return wrapped_lines

    @staticmethod
    def _to_local_time(value: datetime) -> datetime:
        """Convert UTC/naive datetimes to the local timezone for display."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone()


class ChatLog(RichLog):
    """RichLog widget that displays messages and typing indicators."""

    def __init__(
        self,
        self_username: str,
        id: str | None = None,
        *,
        renderer: ChatMessageRenderer | None = None,
    ) -> None:
        """Initialize chat log state and rendering strategy."""
        super().__init__(id=id, highlight=False, auto_scroll=True, wrap=True)
        self.self_username = self_username
        self.renderer = renderer or ChatMessageRenderer()
        self.messages: list[ChatMessage] = []
        self.typing_peers: set[str] = set()

    def append_message(self, message: ChatMessage) -> None:
        """Append one message and immediately re-render the log."""
        self.messages.append(message)
        self.rerender()

    def set_messages(self, messages: list[ChatMessage]) -> None:
        """Replace the full message list and re-render the log."""
        self.messages = list(messages)
        self.rerender()

    def set_message_styles(
        self,
        self_style: str,
        peer_style: str,
        foreground: str | None = None,
    ) -> None:
        """Update message color styles and re-render."""
        self.renderer.self_style = self_style
        self.renderer.peer_style = peer_style
        if foreground is not None:
            self.renderer.foreground = foreground
        self.rerender()

    def set_peer_typing(self, username: str, active: bool) -> None:
        """Track typing state for a peer and re-render indicators."""
        if username == self.self_username:
            return

        if active:
            self.typing_peers.add(username)
        else:
            self.typing_peers.discard(username)

        self.rerender()

    def clear_system_messages(self) -> int:
        """Remove system messages from the current view and re-render."""
        original_count = len(self.messages)
        self.messages = [
            message for message in self.messages if not message.is_system
        ]
        removed_count = original_count - len(self.messages)
        if removed_count:
            self.rerender()
        return removed_count

    def rerender(self) -> None:
        """Repaint all messages and any active typing indicator line."""
        width = max(self.size.width, 1)
        self.clear()

        for message in self.messages:
            for line in self.renderer.render(
                message,
                width=width,
                self_username=self.self_username,
                console=self.app.console,
            ):
                self.write(line)

        if self.typing_peers:
            names = ', '.join(sorted(self.typing_peers))
            suffix = (
                'is typing...'
                if len(self.typing_peers) == 1
                else 'are typing...'
            )
            self.write(Text(f'{names} {suffix}', style='dim italic'))
