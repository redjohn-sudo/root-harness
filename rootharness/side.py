"""
A side question, like /btw: the same agent and model as your conversation,
asked apart from it. No tools, no history of your main conversation, nothing
written into it. Used by the encyclopedia (ask about a word, learn new words).
"""
from __future__ import annotations

import asyncio
import json
import urllib.request

from . import brains

SYSTEM = ("You answer side questions inside root-harness, briefly and clearly, for someone "
          "learning to work with AI agents. Plain words, a concrete example when it helps.")


def ask(brain: dict, model: str | None, messages: list[dict], system: str = SYSTEM, max_tokens: int = 700) -> str:
    """messages: [{"role": "user"|"assistant", "content": "..."}], newest last."""
    if brain["kind"] == "claude":
        return asyncio.run(_claude(model, messages, system))
    if brain["kind"] == "api":
        return _api(brain, model, messages, system, max_tokens)
    raise RuntimeError("Side questions work with Claude Agent or an API agent, not with Codex yet.")


async def _claude(model, messages, system) -> str:
    from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock
    talk = "\n\n".join(("Me: " if m["role"] == "user" else "You: ") + m["content"] for m in messages[:-1])
    prompt = (f"Earlier in this side talk:\n{talk}\n\nNow: " if talk else "") + messages[-1]["content"]
    options = ClaudeAgentOptions(tools=[], setting_sources=[], system_prompt=system, max_turns=1,
                                 model=None if model in (None, "default") else model)
    out = []
    async for m in query(prompt=prompt, options=options):
        if isinstance(m, AssistantMessage):
            out += [b.text for b in m.content if isinstance(b, TextBlock)]
    return "\n".join(out).strip()


def _api(brain, model, messages, system, max_tokens) -> str:
    model = model or (brains.models(brain) or [{}])[0].get("id")
    body = {"model": model, "messages": [{"role": "system", "content": system}, *messages], "max_tokens": max_tokens}
    if brain.get("effort"):
        body["reasoning_effort"] = "low"
    headers = {"Content-Type": "application/json"}
    if brain.get("key"):
        headers["Authorization"] = "Bearer " + brains.key(brain["key"])
    req = urllib.request.Request(brain["url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        return (json.load(r)["choices"][0]["message"].get("content") or "").strip()
