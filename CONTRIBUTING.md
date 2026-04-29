# Contributing

This document captures the practical development workflow for this repo.

## Scope

- The end-user experience is relay-first.
- Local `host` and `join` modes are development/testing paths.

## Workflow Style

- Keep [README.md](README.md) user-focused.
- Put implementation and maintenance detail in this file.
- Prefer small, reviewable commits over large mixed changes.

## Prerequisites

- Python 3.12+
- `uv`

## Source Setup

```bash
uv sync
```

If dependency metadata changes, rebuild the lockfile:

```bash
uv lock
uv sync
```

## Run From Source

Relay mode (default product path):

```bash
uv run python main.py relay --name alice
```

Run two terminals with different names to test chat flow.

Development-only local transport modes:

```bash
uv run python main.py host --port 9000 --name alice
uv run python main.py join --host 127.0.0.1 --port 9000 --name bob
```

## Linting

This repo enforces Google-style docstrings through Ruff.

```bash
uv run ruff check backend frontend main.py api.py
```

## Pull Request Checklist

- Verify user-facing docs still match behavior.
- Run Ruff checks.
- Update [RELEASE_NOTES.md](RELEASE_NOTES.md) for user-visible changes.
- Keep feature flags/caveats accurate for beta status.

## Relay Backend Notes

- FastAPI entrypoint: `api:app`
- WebSocket path: `/api/v1/ws`
- Health endpoint: `/api/v1/health`

The current deployed relay URL is:

`wss://ogham-chat.fastapicloud.dev/api/v1/ws`

## Retention Cleanup

If using Supabase/Postgres for history, apply:

`ops/supabase/purge_expired_chat_messages.sql`

This creates `public.purge_expired_chat_messages(interval)` and schedules
daily cleanup via `pg_cron`.

Manual purge examples:

```bash
DATABASE_URL=postgresql://... uv run python -m backend.maintenance purge-expired
DATABASE_URL=postgresql://... uv run python -m backend.maintenance purge-expired --retention-days 90
```

## Release Notes

- Update `RELEASE_NOTES.md` for user-facing changes.
- Keep README focused on end-user install and usage.

## Beta Release Process

- Use prerelease tags while core features are incomplete (for example, `v0.1.0-beta.1`).
- Mark GitHub releases as prerelease.
- Keep caveats explicit (currently Redis and crypto gaps).