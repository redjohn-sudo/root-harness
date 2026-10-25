"""
The API-key path (secondary to the Claude subscription path in bridge_claude.py).

Most providers speak the OpenAI chat format, so one small client covers OpenAI,
Mistral, Groq, OpenRouter, Nebius, a local llama-server, and so on: just change
`base_url` and the key. The Anthropic API uses its own format.

Status: outline for the roadmap. v1 is centered on the Claude subscription.
Keys are read from environment variables, never hard-coded, never committed.
"""
from __future__ import annotations

import json
import os
import urllib.request


class OpenAICompatible:
    """OpenAI-format chat. Works with OpenAI, Mistral, Groq, OpenRouter, Nebius,
    a local llama-server, etc. Pass the matching base_url and env var name."""

    def __init__(self, model: str, base_url: str = "https://api.openai.com/v1",
                 key_env: str = "OPENAI_API_KEY"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.key = os.environ.get(key_env, "")

    def reply(self, messages: list[dict]) -> str:
        body = json.dumps({"model": self.model, "messages": messages}).encode()
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
        return data["choices"][0]["message"].get("content", "")


# NOTE (roadmap): wire this into a shared run loop so the window can use either
# the Claude subscription (bridge_claude) or an API key (here) behind one switch.
