#!/usr/bin/env python3
"""
Launch root-harness.

    python app.py

Opens a small window where you chat with an AI agent. The agent can read files,
list folders, write files and run commands, and it asks you before anything
that changes your machine.

First run: install Node, then run `claude` once to sign in with your Claude
subscription. See README.md.
"""
from rootharness.window import start

if __name__ == "__main__":
    start()
