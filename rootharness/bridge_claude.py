"""
The Claude bridge: talk to your Claude Pro/Max through the official Claude
Agent SDK, with no terminal.

Claude runs the thinking loop, but it can only act with the small set of tools
we expose here (as an in-process MCP server). Its own built-in tools are off.
Every step is streamed back as an event, so the window can show, in plain
words, what Claude is reading, which tool it wants to run, and what came back.

Setup (one time, per user): install Node and run `claude` (Claude Code) once to
sign in with your Claude subscription. After that this bridge uses that login.
No API key, no extra billing. (Other brains: see brains.py.)
"""
from __future__ import annotations

import asyncio
from typing import Callable

from . import tools, permissions
from .bridge_api import SYSTEM

# Imported lazily so the app can start and show a friendly setup screen even if
# the SDK or the Claude login is not ready yet.
def _sdk():
    from claude_agent_sdk import (  # noqa: F401
        tool, create_sdk_mcp_server, ClaudeAgentOptions, query,
        AssistantMessage, TextBlock, ToolUseBlock, ResultMessage,
    )
    return locals()


def _build_server(sdk, on_event):
    """Expose our REGISTRY tools to Claude as MCP tools."""
    sdk_tools = []
    for name, spec in tools.REGISTRY.items():
        def make(name, spec):
            @sdk["tool"](name, spec["desc"], spec["schema"])
            async def _t(args):
                try:
                    result = tools.run(name, args)
                except Exception as e:
                    result = f"Error: {e}"
                on_event({"type": "result", "name": name, "text": str(result)})
                return {"content": [{"type": "text", "text": str(result)}]}
            return _t
        sdk_tools.append(make(name, spec))
    return sdk["create_sdk_mcp_server"](name="root-harness", tools=sdk_tools)


class Session:
    """A conversation with Claude. The SDK keeps the history on its side; we
    resume the same session id each turn so Claude remembers what was said."""

    def __init__(self, brain: dict):
        self.model = brain.get("model") or None
        self.session_id: str | None = None

    def run_turn(self, prompt: str, on_event: Callable[[dict], None]) -> None:
        asyncio.run(self._turn(prompt, on_event))

    def close(self) -> None:
        pass

    async def _turn(self, prompt: str, on_event: Callable[[dict], None]) -> None:
        """Events (dicts) the UI can render:
          {"type": "text",   "text": ...}               Claude speaking
          {"type": "tool",   "name": ..., "args": ...}  Claude uses a tool
          {"type": "done",   "text": ...}               end of the turn
        """
        sdk = _sdk()
        server = _build_server(sdk, on_event)
        options = sdk["ClaudeAgentOptions"](
            mcp_servers={"root-harness": server},
            # Claude Code's own tools (Bash, Write...) are switched off, and only
            # our MCP server is loaded: Claude can do exactly what tools.py offers.
            tools=[],
            strict_mcp_config=True,
            setting_sources=[],           # none of the user's Claude Code settings
            env={"ENABLE_CLAUDEAI_MCP_SERVERS": "false", "ENABLE_TOOL_SEARCH": "false"},
            system_prompt=SYSTEM,
            allowed_tools=[f"mcp__root-harness__{n}" for n in tools.REGISTRY],
            # Our own tools self-gate through permissions.ask, so the SDK does not
            # add a second prompt. Only our MCP tools are reachable (allowed_tools).
            permission_mode="bypassPermissions",
            model=self.model,
            resume=self.session_id,
        )
        AssistantMessage, ResultMessage = sdk["AssistantMessage"], sdk["ResultMessage"]
        TextBlock, ToolUseBlock = sdk["TextBlock"], sdk["ToolUseBlock"]
        async for message in sdk["query"](prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        on_event({"type": "text", "text": block.text})
                    elif isinstance(block, ToolUseBlock):
                        name = block.name.removeprefix("mcp__root-harness__")
                        on_event({"type": "tool", "name": name, "args": block.input})
            elif isinstance(message, ResultMessage):
                self.session_id = getattr(message, "session_id", None) or self.session_id
                on_event({"type": "done", "text": ""})
