# Ogham Chat ᚛ᚑᚌᚆᚐᚋ᚜

Minimal in-terminal chat app built with Textual.

Version: 0.1.0

## Screenshots

![Ogham Chat](screenshots/Ogham%20Chat.png)

![Slash Commands](screenshots/Slash%20Commands.png)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run in two terminals

Terminal 1 (host):

```bash
python main.py host --port 9000 --name alice
```

Terminal 2 (join):

```bash
python main.py join --host 127.0.0.1 --port 9000 --name bob
```

Both terminals can send messages by typing and pressing Enter.

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
~/.ogham-chat/oghamrc.json
```

This includes:

- Contact groups (`groups_by_user`)
- Last selected UI theme (`theme`)

## Docstring linting

This project enforces Google-style function/class docstrings with Ruff.

Run the check:

```bash
ruff check backend frontend main.py api.py
```

## Run via relay

Use the same TUI and point it at your deployed WebSocket relay endpoint.

Terminal 1:

```bash
python main.py relay --url wss://ogham-chat.fastapicloud.dev/api/v1/ws --name alice
```

Terminal 2:

```bash
python main.py relay --url "wss://ogham-chat.fastapicloud.dev/api/v1/ws" --name bob
```

## Retention cleanup job

If you are storing chat history in Supabase/Postgres, the app now includes both a manual cleanup command and a database-native scheduled job for expired rows.

Apply the scheduler in the Supabase SQL editor:

```sql
-- run ops/supabase/purge_expired_chat_messages.sql
```

That script creates `public.purge_expired_chat_messages(interval)` and schedules it with `pg_cron` to run daily at `00:05 UTC`, deleting rows from `chat_messages` older than 180 days.

You can run the same purge manually against the configured database:

```bash
DATABASE_URL=postgresql://... python -m backend.maintenance purge-expired
```

To keep a different retention window for a one-off run:

```bash
DATABASE_URL=postgresql://... python -m backend.maintenance purge-expired --retention-days 90
```
