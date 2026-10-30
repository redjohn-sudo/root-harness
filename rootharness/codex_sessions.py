"""
Your past Codex conversations, read from the rollout files the Codex CLI keeps
on your machine (~/.codex/sessions/<year>/<month>/<day>/rollout-*.jsonl).

Read-only: we list them and show them again, but Codex cannot resume one of its
own threads, so opening a session starts a fresh Codex thread that is given the
old conversation as context (see the note shown in the window). Nothing here is
ever written back to the rollout files.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
SESSIONS = HOME / "sessions"

# user messages the CLI injects at the start of a thread, not something you typed
_INJECTED = ("# AGENTS.md", "<environment_context>", "<user_instructions>",
             "# Comment travailler", "## My request for Codex")


def _rollouts(limit: int) -> list[Path]:
    try:
        files = [p for p in SESSIONS.rglob("rollout-*.jsonl") if p.is_file()]
    except OSError:
        return []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def _lines(path: Path):
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
    except OSError:
        return


def _text(content) -> str:
    """The text of a message, whatever the content shape Codex used."""
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") in ("input_text", "output_text", "text"):
            parts.append(b.get("text", ""))
    return "".join(parts).strip()


def _is_mine(text: str) -> bool:
    """A message the person actually typed, not an AGENTS.md / context preamble,
    nor a slash-command or harness tag the CLI wraps as a user message."""
    t = text.lstrip()
    return bool(t) and not t.startswith("<") and not t.startswith(_INJECTED)


class Info:
    """What the list needs: enough to show a row and open it later."""
    def __init__(self, session_id: str, title: str, last_modified: int, file_size: int, path: str):
        self.session_id = session_id
        self.title = title
        self.last_modified = last_modified      # milliseconds
        self.file_size = file_size
        self.path = path


def list_sessions(limit: int = 60) -> list[Info]:
    out = []
    for path in _rollouts(limit):
        session_id, title = "", ""
        for o in _lines(path):
            if o.get("type") == "session_meta":
                p = o.get("payload", {})
                session_id = p.get("session_id") or p.get("id") or ""
            elif o.get("type") == "response_item":
                p = o.get("payload", {})
                if p.get("type") == "message" and p.get("role") == "user":
                    txt = _text(p.get("content"))
                    if _is_mine(txt):
                        title = txt[:80]
                        break               # first real prompt is title enough
        if not session_id:
            session_id = path.stem                 # fall back to the file name
        st = path.stat()
        out.append(Info(session_id, title or "Codex session",
                        int(st.st_mtime * 1000), st.st_size, str(path)))
    return out


def _find(session_id: str) -> Path | None:
    for path in _rollouts(400):
        if path.stem.endswith(session_id) or session_id in path.stem:
            return path
    return None


def events(session_id: str, limit: int = 80) -> list[dict]:
    """The conversation as window events (user / text / tool), last `limit` kept."""
    path = Path(session_id) if session_id.endswith(".jsonl") else _find(session_id)
    if not path or not path.exists():
        return []
    out = []
    for o in _lines(path):
        if o.get("type") != "response_item":
            continue
        p = o.get("payload", {})
        kind = p.get("type")
        if kind == "message":
            role = p.get("role")
            txt = _text(p.get("content"))
            if role == "user" and _is_mine(txt):
                out.append({"type": "user", "text": txt})
            elif role == "assistant" and txt:
                out.append({"type": "text", "text": txt})
        elif kind in ("custom_tool_call", "function_call", "local_shell_call"):
            name = p.get("name") or "tool"
            args = p.get("input")
            if isinstance(args, str):
                args = {"input": args[:2000]}
            out.append({"type": "tool", "name": name, "args": args or {}, "done": True})
    return out[-limit:]
