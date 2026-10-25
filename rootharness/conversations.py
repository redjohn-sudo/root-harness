"""
Your conversations and folders, kept on your machine in ~/.root-harness.

  index.json            the list: title, brain, model, folder, dates, and the id
                        the brain needs to continue (Claude session, Codex thread)
  conversations/<id>.json   what the window showed (to show it again), and for
                        API brains the message history (to continue)

Claude Code sessions started in a terminal are listed too (read-only): opening
one continues it in a copy (a "fork"), so the terminal's own session is never
written to.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

HOME = Path.home() / ".root-harness"
INDEX = HOME / "index.json"
FOLDER = HOME / "conversations"


def _load() -> dict:
    try:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("folders", [])
    data.setdefault("conversations", {})
    data.setdefault("hidden", [])           # terminal sessions you removed from the list
    return data


def _save(data: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INDEX)


def now() -> int:
    return int(time.time() * 1000)


# -- conversations ------------------------------------------------------------

def create(brain: str, title: str) -> str:
    data = _load()
    cid = uuid.uuid4().hex[:12]
    data["conversations"][cid] = {"id": cid, "brain": brain, "title": title[:80] or "New conversation",
                                  "created": now(), "updated": now(), "folder": None}
    _save(data)
    return cid


def get(cid: str) -> dict | None:
    return _load()["conversations"].get(cid)


def update(cid: str, **fields) -> None:
    data = _load()
    if cid in data["conversations"]:
        data["conversations"][cid].update(fields, updated=now())
        _save(data)


def adopt_terminal(session_id: str, title: str, updated: int) -> str:
    """A terminal session gets an entry once you move or rename it."""
    data = _load()
    for c in data["conversations"].values():
        if c.get("terminal") == session_id:
            return c["id"]
    cid = uuid.uuid4().hex[:12]
    data["conversations"][cid] = {"id": cid, "brain": "claude", "title": title[:80], "created": updated,
                                  "updated": updated, "folder": None, "terminal": session_id}
    _save(data)
    return cid


def all_listed() -> dict:
    return _load()


def move(cid: str, folder: str | None) -> None:
    data = _load()
    if cid in data["conversations"] and (folder is None or any(f["id"] == folder for f in data["folders"])):
        data["conversations"][cid]["folder"] = folder
        _save(data)


def rename(cid: str, title: str) -> None:
    data = _load()
    if cid in data["conversations"] and title.strip():
        data["conversations"][cid]["title"] = title.strip()[:80]
        _save(data)


def remove(cid: str) -> None:
    """Remove from root-harness. A terminal session stays in Claude Code, only hidden here."""
    data = _load()
    c = data["conversations"].pop(cid, None)
    if c and c.get("terminal"):
        data["hidden"].append(c["terminal"])
    _save(data)
    (FOLDER / f"{cid}.json").unlink(missing_ok=True)


def hide_terminal(session_id: str) -> None:
    data = _load()
    data["hidden"].append(session_id)
    _save(data)


# -- what the window showed, and the history to continue -----------------------

def read_log(cid: str) -> dict:
    try:
        return json.loads((FOLDER / f"{cid}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"events": []}


def write_log(cid: str, log: dict) -> None:
    FOLDER.mkdir(parents=True, exist_ok=True)
    (FOLDER / f"{cid}.json").write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")


# -- folders ------------------------------------------------------------------

def folder_create(name: str) -> dict | None:
    if not name.strip():
        return None
    data = _load()
    f = {"id": uuid.uuid4().hex[:8], "name": name.strip()[:40]}
    data["folders"].append(f)
    _save(data)
    return f


def folder_rename(fid: str, name: str) -> None:
    data = _load()
    for f in data["folders"]:
        if f["id"] == fid and name.strip():
            f["name"] = name.strip()[:40]
    _save(data)


def folder_delete(fid: str) -> None:
    """The folder goes; its conversations go back under their agent."""
    data = _load()
    data["folders"] = [f for f in data["folders"] if f["id"] != fid]
    for c in data["conversations"].values():
        if c.get("folder") == fid:
            c["folder"] = None
    _save(data)
