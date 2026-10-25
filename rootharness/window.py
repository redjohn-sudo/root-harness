"""
The window. A small native window (pywebview / WebKit) that loads the UI and
connects it to the agent. No terminal.

JavaScript calls `window.pywebview.api.*`; Python pushes events back by calling
`onEvent(...)` in the page. Permission questions are shown as a card, and the
tool waits here until the human clicks Allow or Deny.
"""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import webview

from . import permissions, bridge_claude

UI = Path(__file__).parent / "ui" / "index.html"


class Api:
    def __init__(self):
        self._window = None
        self._pending = {}  # permission id -> threading.Event + answer
        self._next = 0
        permissions.set_asker(self._ask)

    def bind(self, window):
        self._window = window

    # -- called from JavaScript --------------------------------------------

    def send(self, prompt: str):
        """The human sent a message. Run one agent turn in the background."""
        threading.Thread(target=self._run, args=(prompt,), daemon=True).start()

    def permission_answer(self, pid: str, allow: bool):
        """The human clicked Allow or Deny on a permission card."""
        slot = self._pending.get(pid)
        if slot:
            slot["allow"] = bool(allow)
            slot["event"].set()

    # -- internals ---------------------------------------------------------

    def _emit(self, event: dict):
        if self._window:
            self._window.evaluate_js(f"onEvent({json.dumps(event)})")

    def _ask(self, title: str, args: dict) -> bool:
        pid = str(self._next); self._next += 1
        ev = threading.Event()
        self._pending[pid] = {"event": ev, "allow": False}
        self._emit({"type": "permission", "id": pid, "title": title, "args": args})
        ev.wait()  # the tool blocks until the human answers
        return self._pending.pop(pid)["allow"]

    def _run(self, prompt: str):
        try:
            asyncio.run(bridge_claude.run_turn(prompt, self._emit))
        except Exception as e:
            self._emit({"type": "error", "text": f"{type(e).__name__}: {e}"})


def start():
    api = Api()
    window = webview.create_window(
        "root-harness", str(UI), js_api=api, width=520, height=680)
    api.bind(window)
    webview.start()
