"""
Connect root-harness to MCP servers (the open Model Context Protocol), so that
every brain, not only Claude, can use external tools: a filesystem server, a
GitHub server, one you wrote yourself. Claude already inherits the MCP servers
of your Claude Code; this gives the same reach to Codex, DeepSeek, Kimi, GLM
and Ollama.

We use the official MCP SDK (the `mcp` package) and nothing heavier: just its
client. Each tool a server offers is added to `tools.REGISTRY` like any native
tool, behind the same permission card, so the agent still asks before it acts.

A server is one subprocess we speak to over stdio. Each keeps its own session,
open on a background event loop for the life of the window, so one can be added
or removed on its own. The rest of the harness sees a plain blocking `run`.
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
_servers: dict[str, dict] = {}   # name -> {"stack", "session", "tools": [registry names]}


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


async def _open(params: StdioServerParameters):
    """Start one server, keep it open on its own stack, return (stack, session, tools)."""
    stack = AsyncExitStack()
    streams = await stack.enter_async_context(stdio_client(params))
    read, write = streams[0], streams[1]
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    listed = await session.list_tools()
    return stack, session, listed


def _text(result) -> str:
    """Pull the plain text out of a CallToolResult."""
    parts = [getattr(c, "text", None) for c in (getattr(result, "content", None) or [])]
    parts = [p for p in parts if p is not None]
    return "\n".join(parts) or "(no output)"


def _schema_of(tool) -> dict:
    raw = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
    props = raw.get("properties", {}) if isinstance(raw, dict) else {}
    return {arg: _PYTYPE.get((spec or {}).get("type"), str) for arg, spec in props.items()}


def _kind_of(tool) -> str:
    """A tool the server marks read-only runs without asking; anything else, or
    anything unmarked, asks first. We trust the hint only to relax, never to
    arm: a missing or false hint stays behind the card."""
    ann = getattr(tool, "annotations", None)
    read_only = None
    if ann is not None:
        read_only = getattr(ann, "read_only_hint", None)
        if read_only is None:
            read_only = getattr(ann, "readOnlyHint", None)
    return permissions.READ_ONLY if read_only is True else permissions.NEEDS_OK


def _register(server: str, session: ClientSession, tool) -> str:
    """Add one MCP tool to the registry, with the right permission level."""
    full = f"{server}__{tool.name}"
    desc = (getattr(tool, "description", None) or f"{tool.name} (MCP server {server})").strip()
    kind = _kind_of(tool)

    def run(**args) -> str:
        if kind == permissions.NEEDS_OK and not permissions.ask(f"Use {tool.name} (MCP: {server})", args):
            return "Denied by the user."
        try:
            return _text(_run(session.call_tool(tool.name, args)))
        except Exception as e:                       # noqa: BLE001
            return f"MCP tool error: {type(e).__name__}: {e}"

    tools.REGISTRY[full] = {"desc": desc, "schema": _schema_of(tool), "kind": kind, "run": run}
    return full


def add_server(name: str, command: str, args=(), env: dict | None = None, deny=()) -> dict:
    """Connect one server and register its tools. Replaces a server of the same
    name. `deny` is a list of tool names to leave out (e.g. destructive ones).
    Returns {ok, tools: [names], error}. Never raises: a bad server just reports
    its error, so one broken server cannot take the others down."""
    _ensure_loop()
    remove_server(name)
    params = StdioServerParameters(command=command, args=list(args), env=env or None)
    try:
        stack, session, listed = _run(_open(params))
    except Exception as e:                           # noqa: BLE001
        return {"ok": False, "tools": [], "error": f"{type(e).__name__}: {e}"}
    blocked = set(deny or ())
    names = [_register(name, session, t) for t in listed.tools if t.name not in blocked]
    _servers[name] = {"stack": stack, "session": session, "tools": names}
    return {"ok": True, "tools": [n.split("__", 1)[1] for n in names], "error": ""}


def remove_server(name: str) -> bool:
    """Unregister a server's tools and close its session."""
    info = _servers.pop(name, None)
    if not info:
        return False
    for full in info["tools"]:
        tools.REGISTRY.pop(full, None)
    try:
        _run(info["stack"].aclose())
    except Exception:                                # noqa: BLE001
        pass
    return True


def status() -> dict:
    """{server name: {tools: [tool names], count}} for the servers now connected."""
    return {name: {"tools": [t.split("__", 1)[1] for t in info["tools"]],
                   "count": len(info["tools"])}
            for name, info in _servers.items()}


def load(servers: dict) -> list[str]:
    """Connect to several servers. servers: {name: {command, args, env}}.
    Returns the full registry names added; skips (and records) the ones that fail."""
    added: list[str] = []
    errors: dict[str, str] = {}
    for name, cfg in servers.items():
        r = add_server(name, cfg["command"], cfg.get("args", []), cfg.get("env"), cfg.get("deny", []))
        if r["ok"]:
            added += [f"{name}__{t}" for t in r["tools"]]
        else:
            errors[name] = r["error"]
    load.errors = errors        # type: ignore[attr-defined]
    return added


def unload() -> None:
    """Remove every MCP server and its tools."""
    for name in list(_servers):
        remove_server(name)
