"""
The brains: which model thinks for your agent.

Same window, same tools, same permission cards. Only the brain changes.
Three kinds:

  - "claude" : your Claude Pro/Max subscription, through the Claude Agent SDK.
               No key: it uses the login of the `claude` CLI.
  - "codex"  : OpenAI's Codex CLI (ChatGPT plan or OpenAI key), through its
               app server. Its approval requests become our Allow / Deny cards.
  - "api"    : any OpenAI-compatible endpoint (DeepSeek, Kimi, GLM, Claude API,
               OpenRouter...) or a local server (Ollama, llama.cpp). Here
               root-harness runs the agent loop itself (see bridge_api.py).

Keys never live in the code. They are read from environment variables, or from
~/.root-harness/.env (readable by you only). To add a brain of your own, put a
list of entries with the same fields in ~/.root-harness/brains.json.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

HOME = Path.home() / ".root-harness"
ENV_FILE = HOME / ".env"
USER_BRAINS = HOME / "brains.json"

# One entry per provider. The model and the effort are picked inside it, with
# /model and /effort (or the brain panel). "models" empty = asked live.
CATALOG: list[dict] = [
    # -- subscriptions: no key --------------------------------------------
    {"id": "claude", "name": "Claude", "kind": "claude", "group": "Subscriptions",
     "note": "Your Claude Pro/Max plan, no key.",
     "models": [{"id": "sonnet", "label": "Sonnet"}, {"id": "opus", "label": "Opus"},
                {"id": "haiku", "label": "Haiku"}],
     "efforts": ["low", "medium", "high", "xhigh", "max"]},
    {"id": "codex", "name": "Codex", "kind": "codex", "group": "Subscriptions",
     "note": "OpenAI's agent, with your ChatGPT plan or OpenAI key.", "models": []},
    # -- API keys ------------------------------------------------------------
    {"id": "deepseek", "name": "DeepSeek", "kind": "api", "group": "API keys",
     "url": "https://api.deepseek.com", "key": "DEEPSEEK_API_KEY", "note": "Cheap and quick.",
     "models": [{"id": "deepseek-flash", "label": "V4.1 Flash"}, {"id": "deepseek-v4-pro", "label": "V4 Pro"}]},
    {"id": "nebius", "name": "Nebius", "kind": "api", "group": "API keys",
     "url": "https://api.studio.nebius.com/v1", "key": "NEBIUS_API_KEY",
     "note": "Open models: Kimi, GLM, Qwen, gpt-oss.",
     "models": [{"id": "moonshotai/Kimi-K3", "label": "Kimi K3"},
                {"id": "zai-org/GLM-5.3-Flash", "label": "GLM-5.3 Flash"},
                {"id": "zai-org/GLM-5.3", "label": "GLM-5.3"},
                {"id": "Qwen/Qwen3.8-27B", "label": "Qwen3.8 27B"},
                {"id": "openai/gpt-oss-120b", "label": "gpt-oss 120B"}],
     # without an effort, some of these spend the whole answer thinking
     "efforts": ["low", "medium", "high"], "effort": "medium"},
    {"id": "claude-api", "name": "Claude API", "kind": "api", "group": "API keys",
     "url": "https://api.anthropic.com/v1", "key": "ANTHROPIC_API_KEY",
     "note": "Claude with a Console key, paid per use.",
     "models": [{"id": "claude-sonnet-5-5", "label": "Sonnet 5.5"}, {"id": "claude-opus-5-5", "label": "Opus 5.5"},
                {"id": "claude-haiku-5-5", "label": "Haiku 5.5"}]},
    # -- local: free, on your machine ---------------------------------------
    {"id": "ollama", "name": "Ollama", "kind": "api", "group": "On your machine",
     "url": "http://localhost:11434/v1", "key": "", "models": [],
     "note": "Any model you pulled with Ollama. Free, offline."},
]

DEFAULT = "claude"
_codex_ok: bool | None = None   # `codex login status` is slow, ask once


def catalog() -> list[dict]:
    extra = []
    try:
        extra = json.loads(USER_BRAINS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return CATALOG + [b for b in extra if isinstance(b, dict) and b.get("id")]


def by_id(ident: str) -> dict | None:
    return next((b for b in catalog() if b["id"] == ident), None)


# -- keys -------------------------------------------------------------------

def key(name: str) -> str:
    """A key from the environment or ~/.root-harness/.env. Never shown."""
    if not name:
        return ""
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def save_key(name: str, value: str) -> bool:
    """Store a key in ~/.root-harness/.env (mode 600), replacing an old one."""
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name or "") or not value.strip():
        return False
    HOME.mkdir(parents=True, exist_ok=True)
    lines = []
    if ENV_FILE.exists():
        lines = [l for l in ENV_FILE.read_text(encoding="utf-8").splitlines()
                 if not l.strip().startswith(name + "=")]
    lines.append(f"{name}={value.strip()}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ENV_FILE.chmod(0o600)
    return True


# -- is it ready? -------------------------------------------------------------

def _local_models(url: str) -> list[str]:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/models", timeout=1.5) as r:
            return [m["id"] for m in json.load(r).get("data", [])]
    except Exception:
        return []


def status(b: dict) -> dict:
    """{"ready": bool, "why": short reason when not ready}. No paid call."""
    global _codex_ok
    if b["kind"] == "claude":
        if shutil.which("claude"):
            return {"ready": True}
        return {"ready": False, "why": "Install Claude Code and sign in once"}
    if b["kind"] == "codex":
        exe = shutil.which("codex")
        if not exe:
            return {"ready": False, "why": "Install the Codex CLI and sign in once"}
        if _codex_ok is None:
            try:
                _codex_ok = subprocess.run([exe, "login", "status"], capture_output=True,
                                           timeout=15).returncode == 0
            except (OSError, subprocess.SubprocessError):
                _codex_ok = False
        return {"ready": True} if _codex_ok else {"ready": False, "why": "Run `codex login` once"}
    if b.get("key"):
        return {"ready": True} if key(b["key"]) else {"ready": False, "why": "Needs a key", "key": b["key"]}
    # keyless API: a local server, it must be running
    return {"ready": True} if _local_models(b["url"]) else {"ready": False, "why": "Not running"}


def models(b: dict) -> list[dict]:
    """The models this brain offers: its list, or what a local server serves."""
    if b.get("models"):
        return b["models"]
    if b["kind"] == "api":
        # embedding models cannot chat, leave them out
        return [{"id": m, "label": m} for m in _local_models(b["url"]) if "embed" not in m.lower()]
    return []


def codex_default_model() -> str:
    """The model in ~/.codex/config.toml, only to show it in the status bar."""
    try:
        text = (Path.home() / ".codex" / "config.toml").read_text(encoding="utf-8")
        m = re.search(r'^model\s*=\s*"([^"]+)"', text, re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def public(b: dict) -> dict:
    """What the window may see (no key values, ever)."""
    return {"id": b["id"], "name": b["name"], "group": b.get("group", "Custom"),
            "note": b.get("note", ""), "kind": b["kind"], **status(b)}


def new_session(b: dict):
    """A conversation with this brain. Each kind keeps its own history."""
    if b["kind"] == "claude":
        from .bridge_claude import Session
    elif b["kind"] == "codex":
        from .bridge_codex import Session
    else:
        from .bridge_api import Session
    return Session(b)
