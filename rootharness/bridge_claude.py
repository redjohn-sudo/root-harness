"""
The Claude bridge: the real Claude Code, on your Claude Pro/Max plan, in a window.

This is the same engine as the `claude` command in a terminal (through the
Claude Agent SDK), with your settings, CLAUDE.md, memory, skills, slash
commands, MCP servers and agents. Nothing is reimplemented. What changes is
where you see it: each tool it uses and each result appear in the window, a
permission question becomes an Allow / Deny card, and when Claude asks you to
choose, the options become buttons.

Setup (one time, per user): install Claude Code and run `claude` once to sign
in with your Claude subscription. No API key, no extra billing.
"""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Callable

from . import permissions

# The permission modes, in the order Shift+Tab cycles them (as in the terminal).
MODES = ["default", "acceptEdits", "plan", "auto"]
EFFORTS_EXTRA = ["ultracode"]   # dynamic workflows, on top of any effort level

# Friendly titles for the permission card.
TITLES = {"Bash": "Run a command", "Write": "Write a file", "Edit": "Edit a file",
          "MultiEdit": "Edit a file", "NotebookEdit": "Edit a notebook",
          "WebFetch": "Open a web page", "WebSearch": "Search the web"}


def _sdk():
    import claude_agent_sdk as sdk
    return sdk


def _short(value, limit: int = 400):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "..."


class Session:
    """One live Claude Code process, kept open across turns, on its own
    asyncio loop so the window never freezes."""

    def __init__(self, brain: dict):
        self.model: str | None = None     # None: your default (from your settings)
        self.effort: str | None = None
        self.mode = "default"
        self.cwd = str(Path.home())
        self.resume_id: str | None = None   # continue this Claude Code session
        self.fork = False                     # True: continue in a copy (terminal sessions)
        self.session_id: str | None = None    # the session this window writes to
        self.client = None
        self.info: dict | None = None
        self.tools: list[str] = []
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self._ready = None

    def _do(self, coro, timeout=None):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    # -- start-up --------------------------------------------------------------

    def start(self) -> None:
        """Start Claude Code in the background (after model/effort/mode are
        set), so the lists are ready when the window asks for them."""
        if self._ready is None:
            self._ready = asyncio.run_coroutine_threadsafe(self._connect(), self.loop)

    async def _connect(self) -> None:
        sdk = _sdk()
        options = sdk.ClaudeAgentOptions(
            setting_sources=["user", "project", "local"],   # your setup, as in the terminal
            system_prompt={"type": "preset", "preset": "claude_code"},
            cwd=self.cwd, model=self.model, permission_mode=self.mode,
            can_use_tool=self._can_use_tool,
            resume=self.resume_id, fork_session=self.fork,
            effort=self.effort if self.effort not in (None, *EFFORTS_EXTRA) else None)
        client = sdk.ClaudeSDKClient(options=options)
        await client.connect()
        self.client = client
        self.info = await client.get_server_info() or {}
        if self.effort in EFFORTS_EXTRA:
            await self._collect(f"/effort {self.effort}")

    def wait_ready(self, timeout: float = 90) -> None:
        self.start()
        self._ready.result(timeout)

    # -- permissions: cards in the window ------------------------------------

    async def _can_use_tool(self, name: str, args: dict, context):
        sdk = _sdk()
        if name == "AskUserQuestion":
            answers = await asyncio.to_thread(permissions.ask_question, args.get("questions", []))
            if answers is None:
                return sdk.PermissionResultDeny(message="The user dismissed the question.")
            return sdk.PermissionResultAllow(updated_input={**args, "answers": answers})
        shown = {k: _short(v) for k, v in args.items()}
        title = TITLES.get(name, f"Use {name.removeprefix('mcp__').replace('__', ' · ')}")
        ok = await asyncio.to_thread(permissions.ask, title, shown)
        if ok:
            return sdk.PermissionResultAllow()
        return sdk.PermissionResultDeny(message="The user said no. Ask what they would prefer.")

    # -- one turn ----------------------------------------------------------------

    def run_turn(self, prompt: str, on_event: Callable[[dict], None], images=None) -> None:
        self.wait_ready()
        self._do(self._turn(prompt, on_event, images or []))

    async def _turn(self, prompt: str, on_event, images: list) -> None:
        sdk = _sdk()
        if images:      # pasted or dropped pictures go with the text
            content = [{"type": "image", "source": {"type": "base64", "media_type": i["media_type"],
                                                     "data": i["data"]}} for i in images]
            content.append({"type": "text", "text": prompt or "Look at this image."})

            async def message():
                yield {"type": "user", "message": {"role": "user", "content": content},
                       "parent_tool_use_id": None}
            await self.client.query(message())
        else:
            await self.client.query(prompt)
        async for m in self.client.receive_response():
            if getattr(m, "parent_tool_use_id", None):
                continue        # inside a sub-agent: the window shows the main thread
            if isinstance(m, sdk.AssistantMessage):
                for b in m.content:
                    if isinstance(b, sdk.TextBlock) and b.text.strip():
                        on_event({"type": "text", "text": b.text})
                    elif isinstance(b, sdk.ToolUseBlock):
                        on_event({"type": "tool", "id": b.id, "name": b.name, "args": b.input})
            elif isinstance(m, sdk.UserMessage) and isinstance(m.content, list):
                for b in m.content:
                    if isinstance(b, sdk.ToolResultBlock):
                        c = b.content
                        if isinstance(c, list):
                            c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
                        on_event({"type": "result", "id": b.tool_use_id, "text": c or ""})
            elif isinstance(m, sdk.SystemMessage):
                if m.subtype == "init":
                    self.tools = m.data.get("tools", [])
                    self.session_id = m.data.get("session_id") or self.session_id
                elif m.subtype == "status" and m.data.get("status"):
                    on_event({"type": "status", "text": m.data["status"]})
            elif isinstance(m, sdk.ResultMessage):
                self.session_id = getattr(m, "session_id", None) or self.session_id
        on_event(await self._usage())
        on_event({"type": "done", "text": ""})

    async def _collect(self, prompt: str) -> str:
        """Run a command and return its text (for /effort...)."""
        sdk = _sdk()
        await self.client.query(prompt)
        out = []
        async for m in self.client.receive_response():
            if isinstance(m, sdk.AssistantMessage):
                out += [b.text for b in m.content if isinstance(b, sdk.TextBlock)]
        return "\n".join(out).strip()

    async def _usage(self) -> dict:
        """How full the context is, as in the terminal's status line."""
        try:
            u = await self.client.get_context_usage()
            return {"type": "usage", "percent": round(u.get("percentage", 0)),
                    "tokens": u.get("totalTokens", 0), "max": u.get("maxTokens", 0)}
        except Exception:
            return {"type": "usage"}

    # -- what the terminal can do ----------------------------------------------

    def interrupt(self) -> None:
        """Esc: stop the current answer."""
        if self.client:
            self._do(self.client.interrupt(), 10)

    def list_models(self) -> list[dict]:
        self.wait_ready()
        models = (self.info or {}).get("models", [])
        out = []
        for m in models:
            label = m.get("displayName", m["value"])
            if m["value"] == "default":   # say which model "default" is
                same = next((x for x in models if x["value"] != "default"
                             and x.get("resolvedModel") == m.get("resolvedModel")), None)
                label = f"Default ({same['displayName']})" if same else label
            out.append({"id": m["value"], "label": label, "desc": m.get("description", ""),
                        "efforts": (m.get("supportedEffortLevels") or []) + EFFORTS_EXTRA,
                        "default": m["value"] == "default"})
        return out

    def list_efforts(self, model: str | None) -> list[str]:
        m = next((m for m in self.list_models() if m["id"] == (model or "default")), None)
        return m["efforts"] if m else EFFORTS_EXTRA

    def commands(self) -> list[dict]:
        """Every slash command of your Claude Code: built-in ones, your skills."""
        self.wait_ready()
        return [{"name": "/" + c["name"], "desc": c.get("description", ""),
                 "hint": c.get("argumentHint", "")}
                for c in (self.info or {}).get("commands", [])]

    def set_model(self, model: str) -> None:
        self.model = None if model == "default" else model
        if self.client:
            self._do(self.client.set_model(self.model), 30)

    def set_effort(self, level: str) -> str:
        self.effort = level
        self.wait_ready()
        return self._do(self._collect(f"/effort {level}"), 60)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if self.client:
            self._do(self.client.set_permission_mode(mode), 10)

    def close(self) -> None:
        async def stop():
            if self.client:
                await self.client.disconnect()
        try:
            self._do(stop(), 10)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
