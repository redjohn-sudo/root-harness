"""
Use root-harness from your phone: the phone is a remote for this computer.

Claude Code cannot run on a phone, so the agent keeps running here, on your
plan, with your tools. The phone (the web app in mobile/) signs in with your
pseudo and password, which gives it your identity, and the two talk through
the same sealed messages as encrypted channels (NIP-59 gift wraps, sent to
yourself). No port to open, no server of ours, from anywhere.

Safety:
  - off by default ("Use from my phone" in Settings);
  - only messages sealed by your own identity are obeyed;
  - a message older than a few minutes, or already seen, is ignored, so a
    relay cannot replay an old order;
  - permission cards still ask: on the phone and here, the first answer wins;
  - sealed messages carry an expiration, so relays may drop them after a day.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

FRESH = 300            # seconds: older orders are ignored
FLUSH = 1.2            # seconds: events are grouped, free relays ban bursts
MAX_TEXT = 3000        # long tool outputs are cut for the phone
FORWARDED = {"text", "tool", "result", "error", "permission", "question", "done", "usage", "status", "remote_user"}


class Remote:
    def __init__(self, api):
        self.api = api
        self.seen: set[str] = set()
        self.buffer: list = []
        self.lock = threading.Lock()
        self.timer = None
        self.phone_seen = 0

    # -- phone -> computer -------------------------------------------------------

    def on_message(self, msg: dict, sender: str, me: str) -> None:
        if sender != me or msg.get("dir") != "phone" or msg.get("v") != 1:
            return
        mid, ts = str(msg.get("id", "")), int(msg.get("ts", 0))
        if not mid or mid in self.seen or abs(time.time() - ts) > FRESH:
            return
        self.seen.add(mid)
        self.phone_seen = int(time.time())
        op = msg.get("op")
        if op == "hello":
            self._send({"op": "state", "state": self.state()})
        elif op == "send" and str(msg.get("text", "")).strip():
            text = str(msg["text"])[:20000]
            if self.api._window:                   # the computer's window shows it too
                self.api._window.evaluate_js(f"onEvent({json.dumps({'type': 'remote_user', 'text': text})})")
            self.api.send(text, None, "phone")
        elif op == "answer":
            if "answers" in msg:
                self.api.question_answer(str(msg.get("pid")), msg.get("answers"))
            else:
                self.api.permission_answer(str(msg.get("pid")), bool(msg.get("allow")))
        elif op == "stop":
            self.api.interrupt()
        elif op == "new":
            self.api.new_conversation()
            self._send({"op": "state", "state": self.state()})

    def state(self) -> dict:
        b = self.api.active_brain()
        events = []
        for e in self.api.log.get("events", [])[-60:]:
            if e.get("type") == "result" and len(e.get("text") or "") > MAX_TEXT:
                e = {**e, "text": e["text"][:MAX_TEXT] + "\n[...]"}
            events.append(e)
        return {"brain": b.get("name"), "model": b.get("label"), "effort": b.get("effort"),
                "mode": b.get("mode"), "busy": self.api._busy.locked(), "events": events}

    # -- computer -> phone -------------------------------------------------------

    def forward(self, event: dict) -> None:
        """Called for every window event; grouped, then sealed and sent."""
        if event.get("type") not in FORWARDED:
            return
        if event.get("type") == "result" and len(event.get("text") or "") > MAX_TEXT:
            event = {**event, "text": event["text"][:MAX_TEXT] + "\n[...]"}
        with self.lock:
            self.buffer.append(event)
            urgent = event["type"] in ("done", "permission", "question", "error")
            if urgent:
                if self.timer:
                    self.timer.cancel()
                    self.timer = None
                threading.Thread(target=self._flush, daemon=True).start()
            elif self.timer is None:
                self.timer = threading.Timer(FLUSH, self._flush)
                self.timer.daemon = True
                self.timer.start()

    def _flush(self) -> None:
        with self.lock:
            events, self.buffer, self.timer = self.buffer, [], None
        if not events:
            return
        # stay under the 64 KB a sealed message can hold
        batch, size = [], 0
        for e in events:
            n = len(json.dumps(e, ensure_ascii=False))
            if batch and size + n > 45000:
                self._send({"op": "events", "events": batch})
                batch, size = [], 0
            batch.append(e)
            size += n
        if batch:
            self._send({"op": "events", "events": batch})

    def _send(self, payload: dict) -> None:
        ch = self.api.channels
        if ch is None:
            return
        payload = {"v": 1, "dir": "computer", "id": uuid.uuid4().hex, "ts": int(time.time()), **payload}
        # a relay may refuse (free relays limit bursts): try again, a bit later each time
        for wait in (0, 2, 5, 10):
            time.sleep(wait)
            try:
                if ch.send_self(payload) > 0:
                    return
            except Exception:
                pass
        self.lost = getattr(self, "lost", 0) + 1
