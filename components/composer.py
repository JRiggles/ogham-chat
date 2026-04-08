from dataclasses import dataclass
from typing import cast

from textual import events
from textual.message import Message
from textual.widgets import TextArea


@dataclass
class ChatComposerSubmit(Message):
    text: str

    def __post_init__(self) -> None:
        Message.__post_init__(self)


class EnterToSubmitMixin:
    async def on_key(self, event: events.Key) -> None:
        # Let Shift+Enter (and any non-Enter key) fall through to TextArea.
        if event.key != 'enter':
            return

        composer = cast(TextArea, self)
        event.prevent_default()
        event.stop()
        composer.post_message(ChatComposerSubmit(composer.text))


class ChatComposer(EnterToSubmitMixin, TextArea):
    pass
