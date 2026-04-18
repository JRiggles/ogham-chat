#!/usr/bin/env python3
"""CLI entrypoint that launches the Textual chat frontend."""

from frontend.chat_tui import main as frontend_main

if __name__ == '__main__':
    frontend_main()
