import textwrap
from dataclasses import dataclass

from rich.text import Text
from textual.widgets import RichLog


@dataclass
class ChatMessage:
    username: str
    text: str
    timestamp: str
    is_system: bool = False


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

        is_self = message.username == self_username
        line_style = self.self_style if is_self else self.peer_style
        header_style = f'bold dim {line_style}'
        name_style = f'bold dim {line_style}'
        body_width = max(width, 1)

        rendered_lines: list[Text] = []

        header = f'{message.username} - {message.timestamp}'
        rendered_header = Text(header, style=header_style)
        name_start = rendered_header.plain.find(message.username)
        if name_start != -1:
            rendered_header.stylize(
                name_style,
                name_start,
                name_start + len(message.username),
            )
        rendered_lines.append(rendered_header)

        wrapped = textwrap.wrap(
            message.text,
            width=body_width,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        ) or ['']

        for chunk in wrapped:
            rendered_lines.append(Text(chunk, style=line_style))

        rendered_lines.append(Text(''))

        return rendered_lines

    def _render_system_message(
        self, message: ChatMessage, width: int
    ) -> list[Text]:
        system_width = max(width, 1)
        wrapped_system = textwrap.wrap(
            message.text,
            width=system_width,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        ) or ['']
        rendered_system = [Text(line, style='dim') for line in wrapped_system]
        rendered_system.append(Text(''))
        return rendered_system


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

    def append_chat_message(
        self, username: str, text: str, timestamp: str
    ) -> None:
        self.messages.append(
            ChatMessage(username=username, text=text, timestamp=timestamp)
        )
        self.rerender()

    def append_system_message(self, text: str, timestamp: str) -> None:
        self.messages.append(
            ChatMessage(
                username='system',
                text=text,
                timestamp=timestamp,
                is_system=True,
            )
        )
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
<<<<<<< HEAD
            suffix = 'is typing...' if len(self.typing_peers) == 1 else 'are typing...'
=======
            suffix = (
                'is typing...'
                if len(self.typing_peers) == 1
                else 'are typing...'
            )
>>>>>>> 088ad79 (feat: implement typing indicator functionality in chat application)
            self.write(Text(f'{names} {suffix}', style='dim italic'))
