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
python chat_tui.py host --port 9000 --name alice
```

Terminal 2 (join):

```bash
python chat_tui.py join --host 127.0.0.1 --port 9000 --name bob
```

Both terminals can send messages by typing and pressing Enter.
