from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option


class ContactSelected(Message):
    def __init__(self, username: str) -> None:
        super().__init__()
        self.username = username


class ContactList(OptionList):
    def __init__(self, self_username: str, id: str | None = None) -> None:
        super().__init__(id=id)
        self.self_username = self_username
        self._users: list[str] = []

    def update_users(self, users: list[str]) -> None:
        selected = self._current_selection()
        self._users = sorted(u for u in users if u != self.self_username)
        self.clear_options()
        for user in self._users:
            self.add_option(Option(user, id=user))
        # Re-select previously selected user if still present.
        if selected and selected in self._users:
            idx = self._users.index(selected)
            self.highlighted = idx

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        event.stop()
        if event.option.id:
            self.post_message(ContactSelected(str(event.option.id)))

    def _current_selection(self) -> str | None:
        if self.highlighted is not None and 0 <= self.highlighted < len(
            self._users
        ):
            return self._users[self.highlighted]
        return None
