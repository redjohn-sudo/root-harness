"""
The window. A small native window (pywebview / WebKit) that loads the UI and
connects it to the agent. No terminal.

JavaScript calls `window.pywebview.api.*`; Python pushes events back by calling
`onEvent(...)` in the page. Permission questions are shown as a card, and the
tool waits here until the human clicks Allow or Deny.
"""
from __future__ import annotations

import json
import shutil
import sys
import subprocess
import threading
from pathlib import Path

import webview

from . import permissions, brains

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
        self._busy = threading.Lock()   # one turn at a time
        self.brain = brains.by_id(read_settings().get("brain", "")) or brains.by_id(brains.DEFAULT)
        self._new_session()
        permissions.set_asker(self._ask)
        permissions.set_questioner(self._question)

    def bind(self, window):
        self._window = window

    # -- called from JavaScript --------------------------------------------

    def send(self, prompt: str):
        """The human sent a message. Run one agent turn in the background."""
        threading.Thread(target=self._run, args=(prompt,), daemon=True).start()

    # -- brains: which model thinks ------------------------------------------

    def _new_session(self):
        """A fresh conversation with the current brain, model, effort and mode."""
        self.session = brains.new_session(self.brain)
        st, bid = read_settings(), self.brain["id"]
        self.session.model = st.get("models", {}).get(bid) or None
        self.session.effort = st.get("efforts", {}).get(bid) or self.brain.get("effort")
        if hasattr(self.session, "mode"):
            self.session.mode = st.get("modes", {}).get(bid) or "default"
        if hasattr(self.session, "start"):
            self.session.start()          # Claude Code starts in the background
        elif not self.session.model:
            first = self._models()
            default = next((m for m in first if m.get("default")), first[0] if first else None)
            self.session.model = default["id"] if default else None

    def _remember(self, key: str, value):
        st = read_settings()
        write_settings(**{key: {**st.get(key, {}), self.brain["id"]: value}})

    def _models(self) -> list[dict]:
        if hasattr(self.session, "list_models"):
            try:
                return self.session.list_models()
            except Exception:
                return []
        return brains.models(self.brain)

    def _efforts(self) -> list[str]:
        if hasattr(self.session, "list_efforts"):
            try:
                return self.session.list_efforts(self.session.model)
            except Exception:
                return []
        return self.brain.get("efforts", [])

    def brains_list(self):
        return {"active": self.brain["id"],
                "brains": [brains.public(b) for b in brains.catalog()]}

    def choose_brain(self, ident: str):
        """Switch brain. The new one starts a fresh conversation."""
        b = brains.by_id(ident)
        if not b or not brains.status(b)["ready"] or self._busy.locked():
            return None
        self.session.close()
        self.brain = b
        self._new_session()
        write_settings(brain=ident)
        return self.active_brain()

    def active_brain(self):
        """Brain, model, effort and mode, for the status bar. Never waits for
        Claude Code to start: until it is up, the label is the model's name."""
        ready = getattr(self.session, "info", True) is not None
        models = self._models() if ready else []
        label = next((m["label"] for m in models if m["id"] == (self.session.model or "default")),
                     self.session.model or "Default")
        return {**brains.public(self.brain), "model": self.session.model, "label": label,
                "effort": self.session.effort or "", "mode": getattr(self.session, "mode", ""),
                "modes": getattr(sys.modules.get(type(self.session).__module__), "MODES", [])}

    def models(self):
        return {"current": self.session.model or "default", "models": self._models()}

    def set_model(self, ident: str):
        """Change the model; the conversation goes on."""
        if self._busy.locked() or ident not in [m["id"] for m in self._models()]:
            return None
        if hasattr(self.session, "set_model"):
            self.session.set_model(ident)
        else:
            self.session.model = ident
        self._remember("models", ident)
        if self.session.effort and self.session.effort not in self._efforts():
            self.session.effort = None
        return self.active_brain()

    def efforts(self):
        return {"current": self.session.effort, "efforts": self._efforts()}

    def set_effort(self, level: str):
        if self._busy.locked() or level not in self._efforts():
            return None
        note = ""
        if hasattr(self.session, "set_effort"):
            note = self.session.set_effort(level)   # Claude Code answers in its own words
        else:
            self.session.effort = level
        self._remember("efforts", level)
        return {**self.active_brain(), "note": note}

    def set_mode(self, mode: str):
        """Permission mode (default, acceptEdits, plan, auto), as Shift+Tab in the terminal."""
        if not hasattr(self.session, "set_mode") or mode not in self.active_brain()["modes"]:
            return None
        self.session.set_mode(mode)
        self._remember("modes", mode)
        return self.active_brain()

    def interrupt(self):
        """Esc: stop the answer in progress."""
        if hasattr(self.session, "interrupt") and self._busy.locked():
            self.session.interrupt()
            return True
        return False

    def commands(self):
        """The brain's own slash commands (for Claude: all of your Claude Code's)."""
        if hasattr(self.session, "commands"):
            try:
                return self.session.commands()
            except Exception:
                return []
        return []

    def clear(self):
        """/clear: forget the conversation, keep brain, model and effort."""
        if self._busy.locked():
            return None
        self.session.close()
        self._new_session()
        return self.active_brain()

    def tools_list(self):
        if getattr(self.session, "tools", None):     # Claude Code's own tools
            return [{"name": n, "desc": "", "asks": False} for n in self.session.tools]
        from . import tools
        return [{"name": n, "desc": t["desc"], "asks": t["kind"] != permissions.READ_ONLY}
                for n, t in tools.REGISTRY.items()]

    def save_key(self, name: str, value: str):
        """Store a key typed in the window, in ~/.root-harness/.env only."""
        return brains.save_key(name, value)

    def question_answer(self, pid: str, answers):
        """The human picked options on a question card ({question: label}),
        or dismissed it (None)."""
        slot = self._pending.get(pid)
        if slot:
            slot["answers"] = answers if isinstance(answers, dict) else None
            slot["event"].set()

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

    def _question(self, questions: list) -> dict | None:
        """The agent asks you to choose: show the options, wait for the pick."""
        pid = str(self._next); self._next += 1
        ev = threading.Event()
        self._pending[pid] = {"event": ev, "answers": None}
        self._emit({"type": "question", "id": pid, "questions": questions})
        ev.wait()
        return self._pending.pop(pid)["answers"]

    def _run(self, prompt: str):
        if not self._busy.acquire(blocking=False):
            self._emit({"type": "error", "text": "Still working on the last message."})
            return
        try:
            self.session.run_turn(prompt, self._emit)
        except Exception as e:
            self._emit({"type": "error", "text": f"{type(e).__name__}: {e}"})
            self._emit({"type": "done", "text": ""})
        finally:
            self._busy.release()


def start():
    api = Api()
    window = webview.create_window(
        "root-harness", str(UI), js_api=api, width=520, height=680)
    api.bind(window)
    webview.start()
