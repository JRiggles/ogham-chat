# Release Notes

## v0.1.0-beta.2 - Beta Release

Release date: 2026-04-28

### Highlights

- Beta update for Ogham Chat.
- Relay-first terminal chat workflow over a WebSocket endpoint.
- Textual-based TUI focused on fast keyboard-driven messaging.
- Packaging updated so Homebrew/pip wheel builds work with this repo layout.

### Beta Caveats

- Redis-backed functionality is not fully integrated yet.
- End-to-end crypto functionality is still incomplete.

### Included

- Interactive TUI chat client with contact list and chat log.
- Contact tree with Online/Offline roots and one-level group organization.
- Slash commands for contacts, groups, and themes.
- Local preference persistence in ~/.ogham-chat/.oghamrc:
	- groups_by_user
	- theme
- FastAPI relay backend with:
	- WebSocket endpoint at /api/v1/ws
	- Health endpoint at /api/v1/health
	- Message APIs used by relay/history flows

### Release Scope

- This is a prerelease intended for early testing.
- Public usage is relay-backed and documented for relay deployments.
- This release establishes the baseline CLI and API behavior for future versions.

### Install and Run

- Fresh install for first-time users.
- Install from Homebrew tap:
	- `brew tap jriggles/ogham-chat`
	- `brew install ogham-chat`
- Launch clients with relay mode, for example:
	- `ogham relay --name alice`
- Relay endpoint is fixed to `wss://ogham-chat.fastapicloud.dev/api/v1/ws`.
