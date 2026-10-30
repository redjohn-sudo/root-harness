"""
Bridge to Instinct, a personal AI assistant you talk to over iMessage.

root-harness has no API to Instinct (there is none public), so this reads and
sends exactly one iMessage conversation: the handle below, and nothing else.

Mac only. Reading needs Full Disk Access (the Messages database); sending needs
Automation permission for Messages (macOS asks once, the first time).

Scope on purpose: every query is filtered to this one handle. We never read
your other conversations.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

def _handle() -> str:
    """The one iMessage handle (phone or email) of your Instinct conversation.
    Never hard-coded here: set INSTINCT_HANDLE, or put it in ~/.root-harness-instinct.
    Empty by default, so the feature stays off until you opt in with your own."""
    h = os.environ.get("INSTINCT_HANDLE", "").strip()
    if h:
        return h
    try:
        return (Path.home() / ".root-harness-instinct").read_text().strip()
    except OSError:
        return ""


HANDLE = _handle()
DB = Path.home() / "Library" / "Messages" / "chat.db"


def available() -> bool:
    """True if a handle is set AND we can open the Messages database (Full Disk Access)."""
    if not HANDLE:
        return False
    try:
        sqlite3.connect(f"file:{DB}?mode=ro", uri=True).close()
        return True
    except sqlite3.Error:
        return False


def _decode_attributed(b: bytes | None) -> str:
    """Pull the plain text out of a message's attributedBody (newer iMessages
    keep the text there, as a streamtyped NSAttributedString, not in `text`)."""
    if not b:
        return ""
    i = b.find(b"NSString")
    if i == -1:
        return ""
    j = b.find(b"+", i)          # the string follows a '+' marker, length-prefixed
    if j == -1:
        return ""
    k = j + 1
    length = b[k]; k += 1
    if length == 0x81:
        length = int.from_bytes(b[k:k + 2], "little"); k += 2
    elif length == 0x82:
        length = int.from_bytes(b[k:k + 4], "little"); k += 4
    return b[k:k + length].decode("utf-8", "replace")


def _rows(where: str, params: tuple, limit: int) -> list[dict]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT m.ROWID, m.is_from_me, m.date, m.text, m.attributedBody "
            "FROM message m JOIN handle h ON m.handle_id = h.ROWID "
            f"WHERE h.id = ? {where} ORDER BY m.ROWID DESC LIMIT ?",
            (HANDLE, *params, limit)).fetchall()
    finally:
        con.close()
    out = []
    for rowid, from_me, _date, text, ab in rows:
        t = (text or "").strip() or _decode_attributed(ab)
        if t.strip():
            out.append({"id": rowid, "from_me": bool(from_me), "text": t})
    out.reverse()                # oldest first
    return out


def history(limit: int = 40) -> list[dict]:
    """The recent messages of the Instinct conversation, oldest first."""
    return _rows("", (), limit)


def since(rowid: int, limit: int = 40) -> list[dict]:
    """Messages after `rowid` (to pick up new replies without re-reading all)."""
    return _rows("AND m.ROWID > ?", (rowid,), limit)


def last_id() -> int:
    """The newest message id in the conversation, or 0 if none / no access."""
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return 0
    try:
        r = con.execute(
            "SELECT MAX(m.ROWID) FROM message m JOIN handle h ON m.handle_id = h.ROWID "
            "WHERE h.id = ?", (HANDLE,)).fetchone()
        return r[0] or 0
    finally:
        con.close()


_SEND = '''on run {target, msg}
  tell application "Messages"
    set svc to 1st account whose service type = iMessage
    send msg to participant target of svc
  end tell
end run'''


def send(text: str) -> tuple[bool, str]:
    """Send one iMessage to Instinct. Returns (ok, error-or-empty)."""
    text = (text or "").strip()
    if not text:
        return False, "Nothing to send."
    try:
        r = subprocess.run(["osascript", "-e", _SEND, HANDLE, text],
                           capture_output=True, text=True, timeout=25)
    except Exception as e:                       # noqa: BLE001
        return False, str(e)
    return (r.returncode == 0), (r.stderr.strip() if r.returncode else "")
