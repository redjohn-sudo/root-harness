"""
Connect root-harness to MCP servers (the open Model Context Protocol), so that
every brain, not only Claude, can use external tools: a filesystem server, a
GitHub server, one you wrote yourself. Claude already inherits the MCP servers
of your Claude Code; this gives the same reach to Codex, DeepSeek, Kimi, GLM
and Ollama.

We use the official MCP SDK (the `mcp` package) and nothing heavier: just its
client. Each tool a server offers is added to `tools.REGISTRY` like any native
tool, behind the same permission card, so the agent still asks before it acts.

A server is one subprocess we speak to over stdio. It gets one task on a
background event loop that owns its session for life: the task opens it, runs
every call, and closes it, all in the same task (the stdio client's cancel
scopes must be entered and exited in one task). The rest of the harness talks
to that task through a queue and sees a plain blocking `run`.
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
_servers: dict[str, dict] = {}   # name -> {"queue", "task", "params", "tools": [registry names]}


def _ensure_loop() -> None:
    """Start the background event loop the MCP sessions live on (once)."""
    global _loop
    if _loop is not None:
        return
    _loop = asyncio.new_event_loop()
    threading.Thread(target=_loop.run_forever, daemon=True, name="mcp").start()


def _submit(coro, timeout: float = 30):
    assert _loop is not None
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout)


async def _serve(params: StdioServerParameters, queue: asyncio.Queue, ready: asyncio.Future) -> None:
    """Own one server's session for its whole life, in this single task: open it,
    answer calls from the queue, and close it here when asked."""
    try:
        async with AsyncExitStack() as stack:
            streams = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
            await session.initialize()
            listed = await session.list_tools()
            ready.set_result(listed)
            while True:
                op = await queue.get()
                if op[0] == "close":
                    op[1].set_result(True)
                    return
                _, tool_name, args, fut = op
                try:
                    fut.set_result(await session.call_tool(tool_name, args))
                except Exception as e:               # noqa: BLE001
                    fut.set_exception(e)
    except Exception as e:                           # noqa: BLE001
        if not ready.done():
            ready.set_exception(e)


async def _start(params: StdioServerParameters):
    queue: asyncio.Queue = asyncio.Queue()
    ready: asyncio.Future = _loop.create_future()
    task = asyncio.ensure_future(_serve(params, queue, ready))
    listed = await ready                              # raises if the server failed to start
    return queue, task, listed


async def _do_call(server: str, tool_name: str, args: dict):
    info = _servers[server]
    fut: asyncio.Future = _loop.create_future()
    await info["queue"].put(("call", tool_name, args, fut))
    # if the owner task ends (server died) the answer would never come: race them
    done, _ = await asyncio.wait({fut, info["task"]}, return_when=asyncio.FIRST_COMPLETED)
    if fut in done:
        return fut.result()
    raise RuntimeError("the MCP server task ended before answering")


async def _do_stop(queue: asyncio.Queue, task: asyncio.Task) -> None:
    fut: asyncio.Future = _loop.create_future()
    await queue.put(("close", fut))
    try:
        await asyncio.wait_for(fut, 5)
    except Exception:                                # noqa: BLE001
        task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(task), 5)
    except Exception:                                # noqa: BLE001
        pass


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


def _reconnect(server: str) -> bool:
    """A server dropped: start it again with the same parameters and swap the
    dead task for the live one. The registry entries are unchanged (they find
    the queue by name), so the tools keep working."""
    info = _servers.get(server)
    if not info:
        return False
    try:
        queue, task, _ = _submit(_start(info["params"]))
    except Exception:                                # noqa: BLE001
        return False
    old_q, old_t = info["queue"], info["task"]
    info["queue"], info["task"] = queue, task
    try:
        _submit(_do_stop(old_q, old_t))
    except Exception:                                # noqa: BLE001
        pass
    return True


def _register(server: str, tool) -> str:
    """Add one MCP tool to the registry, with the right permission level."""
    full = f"{server}__{tool.name}"
    desc = (getattr(tool, "description", None) or f"{tool.name} (MCP server {server})").strip()
    kind = _kind_of(tool)

    def run(**args) -> str:
        if kind == permissions.NEEDS_OK and not permissions.ask(f"Use {tool.name} (MCP: {server})", args):
            return "Denied by the user."
        info = _servers.get(server)
        if info and info["task"].done():             # owner task already gone: revive it first
            _reconnect(server)
        try:
            return _text(_submit(_do_call(server, tool.name, args)))
        except Exception as e:                       # noqa: BLE001
            if _reconnect(server):                   # one retry on a dropped server
                try:
                    return _text(_submit(_do_call(server, tool.name, args)))
                except Exception as e2:              # noqa: BLE001
                    return f"MCP tool error after reconnect: {type(e2).__name__}: {e2}"
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
        queue, task, listed = _submit(_start(params))
    except Exception as e:                           # noqa: BLE001
        return {"ok": False, "tools": [], "error": f"{type(e).__name__}: {e}"}
    blocked = set(deny or ())
    _servers[name] = {"queue": queue, "task": task, "params": params, "tools": []}
    names = [_register(name, t) for t in listed.tools if t.name not in blocked]
    _servers[name]["tools"] = names
    return {"ok": True, "tools": [n.split("__", 1)[1] for n in names], "error": ""}


def remove_server(name: str) -> bool:
    """Unregister a server's tools and close its session."""
    info = _servers.pop(name, None)
    if not info:
        return False
    for full in info["tools"]:
        tools.REGISTRY.pop(full, None)
    try:
        _submit(_do_stop(info["queue"], info["task"]))
    except Exception:                                # noqa: BLE001
        pass
    return True


def status() -> dict:
    """{server name: {tools: [tool names], count}} for the servers now connected."""
    return {name: {"tools": [t.split("__", 1)[1] for t in info["tools"]],
                   "count": len(info["tools"])}
            for name, info in _servers.items()}


def load(servers: dict) -> list[str]:
    """Connect to several servers. servers: {name: {command, args, env, deny}}.
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
