"""
The Codex bridge: OpenAI's Codex CLI, driven through its app server (JSON-RPC,
one JSON message per line on stdin/stdout).

Codex uses its own tools (shell, file edits). We do not hide that: every
command it runs and every file it changes is shown in the window, and anything
risky comes back to us as an approval request, which becomes the same
Allow / Deny card as for the other brains.

Setup (one time): install the Codex CLI and run `codex login`.
"""
from __future__ import annotations

import itertools
import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from . import permissions


class Session:
    def __init__(self, brain: dict):
        self.model: str | None = None     # set by the window (/model); None = Codex's default
        self.effort: str | None = None    # set by the window (/effort)
        self.proc: subprocess.Popen | None = None
        self.thread: str | None = None
        self._ids = itertools.count(1)
        self._changes: dict[str, list] = {}       # fileChange item id -> paths

    # -- JSON-RPC plumbing -----------------------------------------------------

    def _send(self, msg: dict) -> None:
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _read(self) -> dict:
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("Codex stopped. Try `codex login` in a terminal once.")
        return json.loads(line)

    def _request(self, method: str, params: dict) -> dict:
        """Send a request and wait for its answer (start-up only, nothing else
        is expected in between)."""
        rid = next(self._ids)
        self._send({"id": rid, "method": method, "params": params})
        while True:
            msg = self._read()
            if msg.get("id") == rid and "method" not in msg:
                if "error" in msg:
                    raise RuntimeError(f"Codex: {msg['error'].get('message')}")
                return msg.get("result", {})

    def _start(self) -> None:
        exe = shutil.which("codex")
        if not exe:
            raise RuntimeError("The Codex CLI is not installed.")
        self.proc = subprocess.Popen([exe, "app-server"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, bufsize=1)
        self._request("initialize", {"clientInfo": {"name": "root-harness", "version": "0.1"}})
        self._send({"method": "initialized"})
        started = self._request("thread/start", {
            "cwd": str(Path.home()),
            # Codex may read freely; anything else comes back to us to approve.
            "sandbox": "read-only", "approvalPolicy": "on-request",
            "ephemeral": True})
        self.thread = started["thread"]["id"]

    def _ensure(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            self._start()

    def list_models(self) -> list[dict]:
        """The models Codex offers, with the efforts each one supports."""
        self._ensure()
        out = []
        for m in self._request("model/list", {}).get("data", []):
            if m.get("hidden"):
                continue
            efforts = [e.get("reasoningEffort") if isinstance(e, dict) else e
                       for e in m.get("supportedReasoningEfforts") or []]
            out.append({"id": m["id"], "label": m.get("displayName") or m["id"],
                        "efforts": efforts, "default": bool(m.get("isDefault"))})
        return out

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    # -- one turn ----------------------------------------------------------------

    def run_turn(self, prompt: str, on_event: Callable[[dict], None]) -> None:
        self._ensure()
        params = {"threadId": self.thread, "input": [{"type": "text", "text": prompt}]}
        if self.model:
            params["model"] = self.model
        if self.effort:
            params["effort"] = self.effort
        self._send({"id": next(self._ids), "method": "turn/start", "params": params})
        while True:
            msg = self._read()
            method = msg.get("method")
            if method and "id" in msg:            # Codex asks us something
                self._answer(msg, on_event)
            elif method == "item/started":
                self._started(msg["params"]["item"], on_event)
            elif method == "item/completed":
                self._completed(msg["params"]["item"], on_event)
            elif method == "error":
                err = msg["params"].get("error", {})
                on_event({"type": "error", "text": err.get("message", "Codex error")})
            elif method == "turn/completed":
                on_event({"type": "done", "text": ""})
                return
            elif "error" in msg and "id" in msg:  # our turn/start was refused
                raise RuntimeError(f"Codex: {msg['error'].get('message')}")

    def _started(self, item: dict, on_event) -> None:
        kind = item.get("type")
        if kind == "commandExecution":
            on_event({"type": "tool", "name": "shell", "args": {"command": item.get("command")}})
        elif kind == "fileChange":
            paths = [c.get("path") for c in item.get("changes") or []]
            self._changes[item["id"]] = paths
            on_event({"type": "tool", "name": "edit files", "args": {"paths": paths}})
        elif kind == "webSearch":
            on_event({"type": "tool", "name": "web search", "args": {"query": item.get("query")}})
        elif kind in ("mcpToolCall", "dynamicToolCall"):
            on_event({"type": "tool", "name": item.get("tool", kind), "args": item.get("arguments") or {}})

    def _completed(self, item: dict, on_event) -> None:
        kind = item.get("type")
        if kind == "agentMessage" and item.get("text"):
            on_event({"type": "text", "text": item["text"]})
        elif kind == "commandExecution":
            on_event({"type": "result", "name": "shell",
                      "text": item.get("aggregatedOutput") or f"exit code {item.get('exitCode')}"})
        elif kind == "fileChange":
            on_event({"type": "result", "name": "edit files", "text": str(item.get("status", ""))})

    def _answer(self, msg: dict, on_event) -> None:
        method, p = msg["method"], msg.get("params", {})
        if method in ("item/commandExecution/requestApproval", "execCommandApproval"):
            ok = permissions.ask("Run a command", {"command": p.get("command"), "why": p.get("reason")})
        elif method in ("item/fileChange/requestApproval", "applyPatchApproval"):
            ok = permissions.ask("Change files", {"paths": self._changes.get(p.get("itemId"), []),
                                                  "why": p.get("reason")})
        else:
            # Something we do not support yet (questions, extra permissions):
            # say no rather than guess.
            self._send({"id": msg["id"], "error": {"code": -32601, "message": "Not supported by root-harness"}})
            return
        self._send({"id": msg["id"], "result": {"decision": "accept" if ok else "decline"}})
