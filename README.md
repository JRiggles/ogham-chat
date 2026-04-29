# Ogham Chat ᚛ᚑᚌᚆᚐᚋ᚜

Relay-first in-terminal chat app built with Textual.

### Version: 0.1.0-beta.1

**Ogham Chat** is a terminal UI client for person-to-person messaging over an online relay.

## Screenshots

![Ogham Chat](screenshots/Ogham%20Chat.png)

![Slash Commands](screenshots/Slash%20Commands.png)

## Release Scope

- Beta release: not all planned core features are complete.


## Beta Status

Known gaps before stable release:

- Redis-backed features are incomplete or not fully integrated.
- End-to-end crypto flows are incomplete/missing.

## Install (Homebrew Tap)

```bash
brew tap jriggles/ogham-chat
brew install ogham-chat
```

If your tap name differs, use the tap path from your Homebrew tap repository.

## Quickstart (Relay)

Run two terminals and connect both users to the same relay endpoint.

Terminal 1:

```bash
ogham relay --name alice
```

Terminal 2:

```bash
ogham relay --name bob
```

Both terminals can send messages by typing and pressing Enter.

## Hosted Relay

The current relay endpoint is:

`wss://ogham-chat.fastapicloud.dev/api/v1/ws`

## Contact Tree and Groups

The contacts sidebar now uses a tree with two root sections:

- Online
- Offline

Uncategorized contacts appear directly under Online or Offline.

You can manage one-level groups with slash commands:

```text
/group add <username> <group>
/group remove <username> <group>
/group delete <group>
/group list [username]
```

Groups are mirrored under both Online and Offline branches, so the same group name can show online and offline members separately.

Local app preferences persist in a single config file at:

```text
~/.ogham-chat/.oghamrc
```

This includes:

- Contact groups (`groups_by_user`)
- Last selected UI theme (`theme`)

## Core Commands

- `/contact add <username>`
- `/contact remove <username>`
- `/group add <username> <group>`
- `/group remove <username> <group>`
- `/group delete <group>`
- `/group list [username]`
- `/theme list`
- `/theme set <theme_name>`

## Contributing

Developer setup, source workflows, linting, backend operations, and release
details are documented in [CONTRIBUTING.md](CONTRIBUTING.md).
