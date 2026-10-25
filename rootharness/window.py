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
import shutil
import subprocess
import threading
from pathlib import Path

import webview

from . import permissions, bridge_claude

UI = Path(__file__).parent / "ui" / "index.html"
# Your settings live in your home folder, never in the repo.
SETTINGS = Path.home() / ".root-harness" / "settings.json"
IMAGES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif")


def read_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_settings(**changes) -> dict:
    s = read_settings() | changes
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, indent=2), encoding="utf-8")
    return s


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

    # -- settings: the background ------------------------------------------

    def settings_get(self):
        return read_settings()

    def set_background(self, preset: str):
        """One of the built-in looks (a gradient)."""
        return write_settings(background=preset, image="")

    def choose_background(self):
        """Open the file picker and use any image as the background.
        The image is copied next to the UI so the page can load it."""
        mode = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
        picked = self._window.create_file_dialog(
            mode or webview.OPEN_DIALOG, allow_multiple=False,
            file_types=("Images (*.jpg;*.jpeg;*.png;*.webp;*.gif;*.heic;*.heif)",))
        if not picked:
            return None
        src = Path(picked[0])
        if src.suffix.lower() not in IMAGES:
            return None
        for old in UI.parent.glob("background.local.*"):
            old.unlink(missing_ok=True)
        ext = src.suffix.lower()
        try:
            if ext in (".heic", ".heif"):   # iPhone photos: browsers can't show them, convert (macOS)
                dest = UI.parent / "background.local.jpg"
                subprocess.run(["sips", "-s", "format", "jpeg", str(src), "--out", str(dest)],
                               capture_output=True, timeout=30, check=True)
            else:
                dest = UI.parent / f"background.local{ext}"
                shutil.copy(src, dest)
        except (OSError, subprocess.SubprocessError):
            return None
        return write_settings(image=dest.name)

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
