import textwrap

from rich.text import Text
from textual.widgets import RichLog

from backend.types import ChatMessage


class ChatMessageRenderer:
    def __init__(
        self,
        self_style: str = 'green',
        peer_style: str = 'blue',
    ) -> None:
        self.self_style = self_style
        self.peer_style = peer_style

    def render(
        self, message: ChatMessage, width: int, self_username: str
    ) -> list[Text]:
        if message.is_system:
            return self._render_system_message(message, width)

        is_self = message.sender == self_username
        line_style = self.self_style if is_self else self.peer_style
        header_style = f'bold dim {line_style} reverse'
        name_style = f'bold {line_style} reverse'
        body_width = max(width, 1)

        rendered_lines: list[Text] = []

        header = f' {message.sender} - {message.created_at.strftime("%H:%M:%S")} '
        rendered_header = Text(header, style=header_style)
        name_start = rendered_header.plain.find(message.sender)
        if name_start != -1:
            rendered_header.stylize(
                name_style,
                name_start,
                name_start + len(message.sender),
            )
        rendered_lines.append(rendered_header)

        wrapped = self._wrap_preserving_newlines(message.text, body_width)

        for chunk in wrapped:
            rendered_lines.append(Text(chunk, style=line_style))

        rendered_lines.append(Text(''))

        return rendered_lines

    def _render_system_message(
        self, message: ChatMessage, width: int
    ) -> list[Text]:
        system_width = max(width, 1)
        wrapped_system = self._wrap_preserving_newlines(
            message.text, system_width
        )
        rendered_system = [Text(line, style='dim') for line in wrapped_system]
        rendered_system.append(Text(''))
        return rendered_system

    def _wrap_preserving_newlines(self, text: str, width: int) -> list[str]:
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


class ChatLog(RichLog):
    def __init__(
        self,
        self_username: str,
        id: str | None = None,
        *,
        renderer: ChatMessageRenderer | None = None,
    ) -> None:
        super().__init__(id=id, highlight=False, auto_scroll=True, wrap=True)
        self.self_username = self_username
        self.renderer = renderer or ChatMessageRenderer()
        self.messages: list[ChatMessage] = []
        self.typing_peers: set[str] = set()

    def append_message(self, message: ChatMessage) -> None:
        self.messages.append(message)
        self.rerender()

    def set_message_styles(self, self_style: str, peer_style: str) -> None:
        self.renderer.self_style = self_style
        self.renderer.peer_style = peer_style
        self.rerender()

    def set_peer_typing(self, username: str, active: bool) -> None:
        if username == self.self_username:
            return

        if active:
            self.typing_peers.add(username)
        else:
            self.typing_peers.discard(username)

        self.rerender()

    def rerender(self) -> None:
        width = max(self.size.width, 1)
        self.clear()
        for message in self.messages:
            for line in self.renderer.render(
                message, width=width, self_username=self.self_username
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
