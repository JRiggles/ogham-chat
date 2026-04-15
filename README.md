# Ogham Chat ᚛ᚑᚌᚆᚐᚋ᚜

Minimal in-terminal chat app built with Textual.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run in two terminals

Terminal 1 (host):

```bash
python -m frontend.chat_tui host --port 9000 --name alice
```

Terminal 2 (join):

```bash
python -m frontend.chat_tui join --host 127.0.0.1 --port 9000 --name bob
```

Both terminals can send messages by typing and pressing Enter.

## Run via relay

Use the same TUI and point it at your deployed WebSocket relay endpoint.

Terminal 1:

```bash
python -m frontend.chat_tui relay --url wss://ogham-chat.fastapicloud.dev/api/v1/ws --name alice
```

Terminal 2:

```bash
python -m frontend.chat_tui relay --url "wss://ogham-chat.fastapicloud.dev/api/v1/ws" --name bob
```
