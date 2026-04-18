from textual.message import Message
from textual.widgets import Tree
from textual.widgets._tree import TreeNode

NodeData = tuple[str, str]


class ContactSelected(Message):
    """Event emitted when the user selects a contact from the list."""

    def __init__(self, username: str) -> None:
        """Store the selected username on the emitted event."""
        super().__init__()
        self.username = username


class ContactList(Tree[NodeData]):
    """Tree widget that displays online/offline contacts and groups."""

    def __init__(self, self_username: str, id: str | None = None) -> None:
        """Initialize contact list state for the current user."""
        super().__init__('Contacts', id=id)
        self.self_username = self_username
        self.show_root = False
        self.root.expand()

    def update_users(
        self,
        known_users: list[str],
        online_users: set[str],
        groups_by_user: dict[str, set[str]],
    ) -> None:
        """Rebuild tree while preserving selected user leaf when possible."""
        selected = self._current_selection()
        users = sorted(u for u in known_users if u != self.self_username)
        self.clear()
        self.root.expand()

        online_root = self.root.add('Online', data=('status', 'online'))
        offline_root = self.root.add('Offline', data=('status', 'offline'))
        online_root.expand()
        offline_root.expand()

        all_groups = sorted(
            {
                group
                for user in users
                for group in groups_by_user.get(user, set())
                if group
            }
        )

        for user in users:
            target = online_root if user in online_users else offline_root
            user_groups = groups_by_user.get(user, set())
            if user_groups:
                continue
            target.add_leaf(user, data=('user', user))

        for group in all_groups:
            online_group = online_root.add(group, data=('group', f'online:{group}'))
            offline_group = offline_root.add(
                group,
                data=('group', f'offline:{group}'),
            )

            online_group_users = [
                user
                for user in users
                if user in online_users and group in groups_by_user.get(user, set())
            ]
            offline_group_users = [
                user
                for user in users
                if user not in online_users and group in groups_by_user.get(user, set())
            ]

            for user in online_group_users:
                online_group.add_leaf(user, data=('user', user))
            for user in offline_group_users:
                offline_group.add_leaf(user, data=('user', user))

            if online_group_users:
                online_group.expand()
            if offline_group_users:
                offline_group.expand()

        self._restore_selection(selected)

    def on_tree_node_selected(self, event: Tree.NodeSelected[NodeData]) -> None:
        """Emit contact-selected only when a user leaf node is selected."""
        event.stop()
        if not event.node.data:
            return
        node_type, value = event.node.data
        if node_type != 'user':
            return
        self.post_message(ContactSelected(value))

    def _current_selection(self) -> str | None:
        """Return currently selected username leaf if one is selected."""
        node = self.cursor_node
        if node is None or not node.data:
            return None
        node_type, value = node.data
        if node_type != 'user':
            return None
        return value

    def _restore_selection(self, username: str | None) -> None:
        """Restore selection to a matching user leaf node after rebuild."""
        if username is None:
            return
        for node in self._iter_nodes(self.root):
            if not node.data:
                continue
            node_type, value = node.data
            if node_type == 'user' and value == username:
                self.select_node(node)
                return

    def _iter_nodes(self, node: TreeNode[NodeData]) -> list[TreeNode[NodeData]]:
        """Return a depth-first list of descendants for one tree node."""
        result: list[TreeNode[NodeData]] = []
        stack = list(reversed(node.children))
        while stack:
            current = stack.pop()
            result.append(current)
            stack.extend(reversed(current.children))
        return result
