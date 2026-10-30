"""
Connect root-harness to MCP servers (the open Model Context Protocol), so that
every brain, not only Claude, can use external tools: a filesystem server, a
GitHub server, one you wrote yourself. Claude already inherits the MCP servers
of your Claude Code; this gives the same reach to Codex, DeepSeek, Kimi, GLM
and Ollama.

We use the official MCP SDK (the `mcp` package) and nothing heavier: just its
client. Each tool a server offers is added to `tools.REGISTRY` like any native
tool, behind the same permission card, so the agent still asks before it acts.

A server is one subprocess we speak to over stdio. We keep the sessions open on
a background event loop for the life of the window, and expose a plain blocking
`run` to the rest of the harness.
"""
from __future__ import annotations

import asyncio
import threading
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import permissions, tools

# JSON Schema type -> the Python type tools.py uses in a tool's `schema`
# (bridge_api maps it back to a JSON type for the model).
_PYTYPE = {"string": str, "integer": int, "number": float,
           "boolean": bool, "array": list, "object": dict}

_loop: asyncio.AbstractEventLoop | None = None
_stack: AsyncExitStack | None = None
_sessions: dict[str, ClientSession] = {}
_loaded: list[str] = []          # tool names we added, so we can remove them


def _ensure_loop() -> None:
    """Start the background event loop the MCP sessions live on (once)."""
    global _loop
    if _loop is not None:
        return
    _loop = asyncio.new_event_loop()
    threading.Thread(target=_loop.run_forever, daemon=True, name="mcp").start()


def _run(coro, timeout: float = 30):
    assert _loop is not None
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout)


async def _connect(name: str, params: StdioServerParameters):
    """Open one server, keep it open on the exit stack, return its tool list."""
    assert _stack is not None
    streams = await _stack.enter_async_context(stdio_client(params))
    read, write = streams[0], streams[1]
    session = await _stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    _sessions[name] = session
    return await session.list_tools()


def _text(result) -> str:
    """Pull the plain text out of a CallToolResult."""
    parts = [getattr(c, "text", None) for c in (getattr(result, "content", None) or [])]
    parts = [p for p in parts if p is not None]
    return "\n".join(parts) or "(no output)"


def _schema_of(tool) -> dict:
    raw = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
    props = raw.get("properties", {}) if isinstance(raw, dict) else {}
    return {arg: _PYTYPE.get((spec or {}).get("type"), str) for arg, spec in props.items()}


def _register(server: str, tool) -> str:
    """Add one MCP tool to the registry, behind a permission card."""
    name = f"{server}__{tool.name}"
    desc = (getattr(tool, "description", None) or f"{tool.name} (MCP server {server})").strip()

    def run(**args) -> str:
        if not permissions.ask(f"Use {tool.name} (MCP: {server})", args):
            return "Denied by the user."
        try:
            return _text(_run(_sessions[server].call_tool(tool.name, args)))
        except Exception as e:                       # noqa: BLE001
            return f"MCP tool error: {type(e).__name__}: {e}"

    tools.REGISTRY[name] = {"desc": desc, "schema": _schema_of(tool),
                            "kind": permissions.NEEDS_OK, "run": run}
    _loaded.append(name)
    return name


def load(servers: dict) -> list[str]:
    """Connect to MCP servers and register their tools.

    servers: {name: {"command": str, "args": [str, ...], "env": {str: str}}}.
    Returns the list of tool names added to the registry. A server that fails to
    start is skipped (its error is raised to the caller for the first one only;
    callers that load several should catch per server)."""
    global _stack
    _ensure_loop()
    if _stack is None:
        _stack = AsyncExitStack()
    added: list[str] = []
    for name, cfg in servers.items():
        params = StdioServerParameters(
            command=cfg["command"], args=list(cfg.get("args", [])),
            env=cfg.get("env") or None)
        listed = _run(_connect(name, params))
        for tool in listed.tools:
            added.append(_register(name, tool))
    return added


def unload() -> None:
    """Remove every MCP tool and close all sessions."""
    global _stack
    for name in _loaded:
        tools.REGISTRY.pop(name, None)
    _loaded.clear()
    _sessions.clear()
    if _stack is not None:
        try:
            _run(_stack.aclose())
        except Exception:                            # noqa: BLE001
            pass
        _stack = None
