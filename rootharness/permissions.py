"""
The permission gate.

Every tool that touches the system (writes a file, runs a command) must pass
through here first. The gate asks a question and waits for a yes or no. The
window hooks into `set_asker` so the question is shown as a clear card in the
interface, not hidden in a terminal. This is the one idea we want every
beginner to internalise: an agent only acts when you let it.
"""
from __future__ import annotations

from typing import Callable

# A tool is READ_ONLY (safe, runs without asking) or NEEDS_OK (ask first).
READ_ONLY = "read_only"
NEEDS_OK = "needs_ok"

# The function the UI provides to ask the human. It receives a short title and
# a dict of arguments, and returns True (allow) or False (deny). The default
# denies everything, so a missing UI never silently runs a risky tool.
_asker: Callable[[str, dict], bool] = lambda title, args: False


def set_asker(fn: Callable[[str, dict], bool]) -> None:
    """The window calls this once to route permission questions to the UI."""
    global _asker
    _asker = fn


def ask(title: str, args: dict) -> bool:
    """Ask the human. Returns True if allowed."""
    try:
        return bool(_asker(title, args))
    except Exception:
        return False


# Questions: sometimes the agent asks you to choose (e.g. "which approach?").
# The window shows the options as buttons and returns {question: chosen label},
# or None if you dismiss it.
_questioner: Callable[[list], dict | None] = lambda questions: None


def set_questioner(fn: Callable[[list], dict | None]) -> None:
    global _questioner
    _questioner = fn


def ask_question(questions: list) -> dict | None:
    try:
        return _questioner(questions)
    except Exception:
        return None
