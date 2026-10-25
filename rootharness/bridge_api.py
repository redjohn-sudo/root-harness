"""
The API-key path: any OpenAI-compatible chat endpoint (DeepSeek, Kimi, GLM,
the Claude API, OpenRouter, a local Ollama...).

Claude and Codex run their own agent loop. Here root-harness runs it, and it is
short enough to read in one go: send the conversation and the tool list, run
the tools the model asks for, send the results back, repeat until it answers.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

from . import brains, tools

MAX_STEPS = 12
SYSTEM = ("You are an agent running inside root-harness, on the user's computer. "
          "Use the tools when they help. Tools that change the machine ask the user first; "
          "if the user denies, respect it and suggest another way.")
_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def tool_specs() -> list[dict]:
    """Our REGISTRY in the OpenAI function-calling format."""
    specs = []
    for name, spec in tools.REGISTRY.items():
        props = {k: {"type": _TYPES.get(t, "string")} for k, t in spec["schema"].items()}
        specs.append({"type": "function", "function": {
            "name": name, "description": spec["desc"],
            "parameters": {"type": "object", "properties": props, "required": list(props)}}})
    return specs


class Session:
    def __init__(self, brain: dict):
        self.brain = brain
        self.model: str | None = None     # set by the window (/model)
        self.effort: str | None = None    # set by the window (/effort)
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM}]

    def close(self) -> None:
        pass

    def _call(self) -> dict:
        b = self.brain
        body = {"model": self.model, "messages": self.messages,
                "tools": tool_specs(), "tool_choice": "auto", "max_tokens": 4000}
        if self.effort:
            body["reasoning_effort"] = self.effort
        headers = {"Content-Type": "application/json"}
        if b.get("key"):
            headers["Authorization"] = "Bearer " + brains.key(b["key"])
        req = urllib.request.Request(b["url"].rstrip("/") + "/chat/completions",
                                     data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)["choices"][0]["message"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"{b['name']} answered {e.code}: {detail}") from None

    def run_turn(self, prompt: str, on_event: Callable[[dict], None], images=None) -> None:
        if not self.model:
            raise RuntimeError(f"{self.brain['name']}: no model found (is it running?)")
        if images:      # OpenAI format; only models that see images accept it
            content = [{"type": "image_url", "image_url": {
                "url": f"data:{i['media_type']};base64,{i['data']}"}} for i in images]
            content.append({"type": "text", "text": prompt or "Look at this image."})
            self.messages.append({"role": "user", "content": content})
        else:
            self.messages.append({"role": "user", "content": prompt})
        for _ in range(MAX_STEPS):
            msg = self._call()
            # keep the message as the provider sent it (some need their own
            # fields back, like reasoning_content), minus empty values
            self.messages.append({k: v for k, v in msg.items() if v is not None})
            if msg.get("content"):
                on_event({"type": "text", "text": msg["content"]})
            calls = msg.get("tool_calls") or []
            if not calls:
                on_event({"type": "done", "text": ""})
                return
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                on_event({"type": "tool", "name": name, "args": args})
                try:
                    result = tools.run(name, args)
                except Exception as e:
                    result = f"Error: {e}"
                on_event({"type": "result", "name": name, "text": str(result)})
                self.messages.append({"role": "tool", "tool_call_id": call["id"],
                                      "content": str(result)})
        on_event({"type": "text", "text": f"(Stopped after {MAX_STEPS} steps.)"})
        on_event({"type": "done", "text": ""})
