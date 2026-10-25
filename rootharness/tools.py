"""
A small set of safe starter tools.

They are deliberately simple and few, so a beginner can read every one and
understand exactly what the agent can do. Read-only tools run freely; anything
that changes the system asks for permission first through `permissions.ask`.

Add your own tool: write a function, wrap it with @register, done. See
examples/add_your_own_tool.py.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import permissions

# The registry: name -> {desc, schema, kind, run}. The bridge reads this to
# expose the tools to the model.
REGISTRY: dict[str, dict] = {}


def register(name: str, desc: str, schema: dict, kind: str = permissions.NEEDS_OK):
    def deco(fn):
        REGISTRY[name] = {"desc": desc, "schema": schema, "kind": kind, "run": fn}
        return fn
    return deco


# ---- read-only tools: run without asking -----------------------------------

@register("read_file", "Read a text file and return its content.",
          {"path": str}, kind=permissions.READ_ONLY)
def read_file(path: str) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")[:20000]


@register("list_dir", "List the files in a folder.",
          {"path": str}, kind=permissions.READ_ONLY)
def list_dir(path: str) -> str:
    p = Path(path).expanduser()
    return "\n".join(sorted(os.listdir(p)))


# ---- tools that change things: ask first -----------------------------------

@register("write_file", "Write text to a file (creates or overwrites it).",
          {"path": str, "content": str})
def write_file(path: str, content: str) -> str:
    if not permissions.ask("Write a file", {"path": path, "size": f"{len(content)} chars"}):
        return "Denied by the user."
    Path(path).expanduser().write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}."


@register("run_command", "Run a shell command and return its output.",
          {"command": str})
def run_command(command: str) -> str:
    if not permissions.ask("Run a command", {"command": command}):
        return "Denied by the user."
    out = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    return (out.stdout + out.stderr)[:20000] or "(no output)"


def run(name: str, args: dict) -> str:
    """Execute a tool by name. Read-only tools skip the question."""
    spec = REGISTRY.get(name)
    if not spec:
        return f"Unknown tool: {name}"
    return spec["run"](**args)
