"""
The Claude bridge: talk to your Claude Pro/Max through the official Claude
Agent SDK, with no terminal.

Claude runs the thinking loop, but it can only act with the small set of tools
we expose here (as an in-process MCP server). Its own built-in tools are off.
Every step is streamed back as an event, so the window can show, in plain
words, what Claude is reading, which tool it wants to run, and what came back.

Setup (one time, per user): install Node and run `claude` (Claude Code) once to
sign in with your Claude subscription. After that this bridge uses that login.
No API key, no extra billing. (The API-key path lives in models.py instead.)
"""
from __future__ import annotations

from typing import Callable

from . import tools, permissions

# Imported lazily so the app can start and show a friendly setup screen even if
# the SDK or the Claude login is not ready yet.
def _sdk():
    from claude_agent_sdk import (  # noqa: F401
        tool, create_sdk_mcp_server, ClaudeAgentOptions, query,
        AssistantMessage, TextBlock, ToolUseBlock, ResultMessage,
    )
    return locals()


def _build_server(sdk):
    """Expose our REGISTRY tools to Claude as MCP tools."""
    sdk_tools = []
    for name, spec in tools.REGISTRY.items():
        def make(name, spec):
            @sdk["tool"](name, spec["desc"], spec["schema"])
            async def _t(args):
                result = tools.run(name, args)
                return {"content": [{"type": "text", "text": str(result)}]}
            return _t
        sdk_tools.append(make(name, spec))
    return sdk["create_sdk_mcp_server"](name="root-harness", tools=sdk_tools)


async def run_turn(prompt: str, on_event: Callable[[dict], None]) -> None:
    """Run one user turn through Claude, emitting events as it goes.

    Events (dicts) the UI can render:
      {"type": "text",   "text": ...}            Claude speaking
      {"type": "tool",   "name": ..., "args": ...}  Claude wants to use a tool
      {"type": "result", "name": ..., "text": ...}  what the tool returned
      {"type": "done",   "text": ...}            end of the turn
    """
    sdk = _sdk()
    server = _build_server(sdk)
    options = sdk["ClaudeAgentOptions"](
        mcp_servers={"root-harness": server},
        # Only our tools are allowed; Claude Code's native tools stay off.
        allowed_tools=[f"mcp__root-harness__{n}" for n in tools.REGISTRY],
        # Our own tools self-gate through permissions.ask, so the SDK does not
        # add a second prompt. Only our MCP tools are reachable (allowed_tools).
        permission_mode="bypassPermissions",
    )
    async for message in sdk["query"](prompt=prompt, options=options):
        AssistantMessage = sdk["AssistantMessage"]
        TextBlock, ToolUseBlock = sdk["TextBlock"], sdk["ToolUseBlock"]
        ResultMessage = sdk["ResultMessage"]
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    on_event({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    on_event({"type": "tool", "name": block.name, "args": block.input})
        elif isinstance(message, ResultMessage):
            on_event({"type": "done", "text": getattr(message, "result", "") or ""})

# NOTE (M1): confirm the exact event/permission hooks against the installed
# claude-agent-sdk version. The tool result is already gated by permissions.ask
# inside tools.py, so a risky tool always asks the human first.
