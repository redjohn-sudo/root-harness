"""
Encrypted channels between root-harness users, over Nostr (NIP-17 private
messages, NIP-44 encryption, NIP-59 gift wraps).

  - Your identity is a key made on your machine and locked with your password
    (see account.py). No server account, no email, no phone number.
  - A message is sealed for each member separately. Public relays carry it but
    only see an encrypted blob from a throwaway key: not the text, not who sent
    it, not the channel's name or members.
  - You add people by their public ID (npub...). Messages from someone you have
    not added land in "Requests" until you accept them.

What relays still see: your IP address and when you connect, and that some
blob is addressed to your public key. A stolen secret key would open past
messages too (no forward secrecy), which is why it is locked by your password.

Your pseudo travels inside the sealed message. Anyone can claim any pseudo, so
the name you give a contact is the one shown; a stranger's pseudo is shown
with their ID next to it.

The agent never reads or sends in a channel by itself: sending is always a
human click.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Callable

HOME = Path(os.environ.get("ROOT_HARNESS_HOME") or Path.home() / ".root-harness")
STATE = HOME / "channels.json"
LOGS = HOME / "channels"
RELAYS = ["wss://relay.damus.io", "wss://nos.lol", "wss://relay.primal.net"]
LOOKBACK = 3 * 86400        # gift wraps are back-dated up to 2 days (NIP-59)


async def _aw(x):
    return await x if inspect.isawaitable(x) else x


def _n():
    import nostr_sdk
    return nostr_sdk


def _hex_of(npub_or_hex: str) -> str | None:
    try:
        return _n().PublicKey.parse(npub_or_hex.strip()).to_hex()
    except Exception:
        return None


def _npub(hexkey: str) -> str:
    return _n().PublicKey.parse(hexkey).to_bech32()


def channel_id(members: set[str]) -> str:
    """A channel is its set of members (you included)."""
    return hashlib.sha256(",".join(sorted(members)).encode()).hexdigest()[:16]


# -- local state ----------------------------------------------------------------

def _load() -> dict:
    try:
        s = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    s.setdefault("contacts", {})      # hex -> {"name"}
    s.setdefault("channels", {})      # id -> {"name", "members": [hex, ...] (not you), "unread", "last", "request"}
    s.setdefault("relays", RELAYS)
    s.setdefault("seen", [])          # gift wrap ids already handled
    s.setdefault("pseudos", {})       # hex -> the pseudo they announce (not trusted)
    return s


on_change = lambda: None     # the window points this at the sync


def _save(s: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    s["seen"] = s["seen"][-3000:]
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE)
    on_change()


def _read_log(cid: str) -> list:
    try:
        return json.loads((LOGS / f"{cid}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _append(cid: str, msg: dict) -> bool:
    log = _read_log(cid)
    if any(m["rid"] == msg["rid"] for m in log):
        return False
    log.append(msg)
    log.sort(key=lambda m: m["at"])
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / f"{cid}.json").write_text(json.dumps(log[-2000:], ensure_ascii=False), encoding="utf-8")
    return True


class Channels:
    """Runs the Nostr client on its own loop; calls on_event for the window."""

    def __init__(self, on_event: Callable[[dict], None], keys, pseudo: str = ""):
        self.on_event = on_event
        self.keys = keys                  # unlocked by your password (account.py)
        self.pseudo = pseudo
        self.on_remote = None             # remote.py: orders from your phone
        self.last_refused: dict = {}
        self.lock = threading.Lock()
        self.me = keys.public_key().to_hex()
        self.client = None
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self._ready = asyncio.run_coroutine_threadsafe(self._start(), self.loop)

    def _do(self, coro, timeout=30):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    # -- connection and listening --------------------------------------------

    async def _start(self) -> None:
        n = _n()
        self.client = n.ClientBuilder().build()
        for r in _load()["relays"]:
            await _aw(self.client.add_relay(n.RelayUrl.parse(r)))
        await _aw(self.client.connect(and_wait=timedelta(seconds=6)))
        since = n.Timestamp.from_secs(int(time.time()) - LOOKBACK)
        f = n.Filter().kind(n.Kind(1059)).pubkey(self.keys.public_key()).since(since)
        # catch up on what arrived while root-harness was closed, then listen
        for ev in await self._fetch(f):
            await self._receive(ev)
        await _aw(self.client.subscribe(n.ReqTarget.auto([f])))
        asyncio.ensure_future(self._listen())
        self.on_event({"type": "channels_ready"})

    async def _fetch(self, f) -> list:
        evs = await _aw(self.client.fetch_events(_n().ReqTarget.auto([f]), timeout=timedelta(seconds=8)))
        return evs.to_vec() if hasattr(evs, "to_vec") else list(evs)

    async def _listen(self) -> None:
        stream = await _aw(self.client.notifications())
        while True:
            note = await _aw(stream.next())
            if note is None:
                break
            if note.is_new_event():
                ev = getattr(note, "event", None)
                if ev is not None and ev.kind().as_u16() == 1059:
                    await self._receive(ev)

    async def _receive(self, ev) -> None:
        n = _n()
        wid = ev.id().to_hex()
        with self.lock:
            s = _load()
            if wid in s["seen"]:
                return
            s["seen"].append(wid)
            _save(s)
        try:
            gift = await _aw(n.UnwrappedGift.from_gift_wrap(self.keys, ev))
        except Exception:
            return              # not for us, or tampered with: ignore
        rumor, sender = gift.rumor(), gift.sender().to_hex()
        if rumor.kind().as_u16() != 14:
            return
        tags = rumor.tags()
        if any(t.kind() == "rh-op" for t in tags):
            if sender == self.me:          # one of your devices added a friend or a group
                try:
                    self._apply(json.loads(rumor.content()))
                except (ValueError, TypeError, KeyError):
                    pass
                self.on_event({"type": "channels_changed"})
            return
        if any(t.kind() == "rh-remote" for t in tags):
            # your phone talking to this computer: not a channel message
            if self.on_remote and sender == self.me:
                try:
                    order = json.loads(rumor.content())
                except (ValueError, TypeError):
                    return
                # handled off this loop: answering needs the loop to send
                threading.Thread(target=self.on_remote, args=(order, sender, self.me), daemon=True).start()
            return
        members = {t.content() for t in tags if t.kind() == "p" and t.content()} | {sender, self.me}
        rid = next((t.content() for t in tags if t.kind() == "rh-id"), None) or wid
        subject = next((t.content() for t in tags if t.kind() == "subject"), None)
        their = next((t.content() for t in tags if t.kind() == "rh-name"), None)
        cid = channel_id(members)
        with self.lock:
            s = _load()
            if their and sender != self.me:
                s["pseudos"][sender] = their[:32]
            ch = s["channels"].get(cid)
            if ch is None:
                others = sorted(members - {self.me})
                known = all(o in s["contacts"] for o in others)
                ch = s["channels"][cid] = {"name": subject or "", "members": others, "unread": 0,
                                           "last": 0, "request": not known and sender != self.me}
            if subject and subject != ch["name"] and sender != self.me:
                ch["name"] = subject
            at = rumor.created_at().as_secs()
            msg = {"rid": rid, "from": sender, "text": rumor.content(), "at": at}
            if any(t.kind() == "rh-share" for t in tags):
                try:
                    share = json.loads(rumor.content())
                    msg = {**msg, "text": "shared: " + str(share.get("title", "")), "share": share}
                except (ValueError, TypeError):
                    pass
            new = _append(cid, msg)       # our own copy comes back too: shown once
            if new:
                ch["last"] = max(ch["last"], at)
                if sender != self.me:
                    ch["unread"] += 1
            _save(s)
        if new:
            self.on_event({"type": "channel_message", "channel": cid, "message": self._view(msg)})

    # -- what the window calls --------------------------------------------------

    def ready(self, timeout=40) -> bool:
        try:
            self._ready.result(timeout)
            return True
        except Exception:
            return False

    def _name(self, hexkey: str, s: dict | None = None) -> str:
        if hexkey == self.me:
            return "You"
        s = s or _load()
        c = s["contacts"].get(hexkey)
        if c:
            return c["name"]
        short = _npub(hexkey)[:14] + "..."
        p = s["pseudos"].get(hexkey)
        return f"{p} ({short})" if p else short

    def _view(self, m: dict) -> dict:
        return {**m, "mine": m["from"] == self.me, "name": self._name(m["from"])}

    def identity(self) -> dict:
        if not self.ready():
            return {}
        async def count():
            relays = await _aw(self.client.relays())
            n = _n()
            return sum([await _aw(r.status()) == n.RelayStatus.CONNECTED for r in relays.values()])
        try:
            connected = self._do(count(), 10)
        except Exception:
            connected = 0
        return {"npub": _npub(self.me), "relays": len(_load()["relays"]), "connected": connected}

    def overview(self) -> dict:
        s = _load()
        chans = []
        for cid, ch in s["channels"].items():
            log = _read_log(cid)
            last = log[-1] if log else None
            chans.append({"id": cid, "name": ch["name"] or ", ".join(self._name(m, s) for m in ch["members"]),
                          "members": [{"hex": m, "name": self._name(m, s), "npub": _npub(m),
                                       "pseudo": s["pseudos"].get(m, "")} for m in ch["members"]],
                          "unread": ch["unread"], "last": ch["last"], "request": ch.get("request", False),
                          "preview": (self._name(last["from"], s) + ": " + last["text"])[:80] if last else ""})
        chans.sort(key=lambda c: -c["last"])
        contacts = [{"hex": h, "name": c["name"], "npub": _npub(h)} for h, c in s["contacts"].items()]
        return {"channels": chans, "contacts": sorted(contacts, key=lambda c: c["name"].lower())}

    def add_contact(self, npub: str, name: str) -> dict | None:
        h = _hex_of(npub)
        if not h or not name.strip() or (self.me and h == self.me):
            return None
        self._announce({"op": "contact_add", "hex": h, "name": name.strip()[:40]})
        with self.lock:
            s = _load()
            s["contacts"][h] = {"name": name.strip()[:40]}
            for ch in s["channels"].values():     # their requests become normal channels
                if all(m in s["contacts"] for m in ch["members"]):
                    ch["request"] = False
            _save(s)
        return {"hex": h, "name": name.strip()[:40]}

    def create_channel(self, name: str, members: list[str]) -> str | None:
        s = _load()
        members = [m for m in members if m in s["contacts"]]
        if not members or not self.ready():
            return None
        cid = channel_id(set(members) | {self.me})
        self._announce({"op": "group_create", "name": name.strip()[:60], "members": sorted(members)})
        with self.lock:
            s = _load()
            s["channels"].setdefault(cid, {"name": name.strip()[:60], "members": sorted(members),
                                           "unread": 0, "last": int(time.time()), "request": False})
            _save(s)
        return cid

    def messages(self, cid: str) -> list:
        with self.lock:
            s = _load()
            if cid in s["channels"]:
                s["channels"][cid]["unread"] = 0
                _save(s)
        return [self._view(m) for m in _read_log(cid)]

    def accept(self, cid: str) -> bool:
        with self.lock:
            s = _load()
            if cid in s["channels"]:
                s["channels"][cid]["request"] = False
                _save(s)
        return True

    def send(self, cid: str, text: str, share: dict | None = None) -> dict | None:
        """Seal the message once per member (and once for you, for your other
        devices), then hand the sealed copies to the relays."""
        if not text.strip() or not self.ready():
            return None
        s = _load()
        ch = s["channels"].get(cid)
        if not ch:
            return None
        rid = uuid.uuid4().hex
        msg = {"rid": rid, "from": self.me, "text": text, "at": int(time.time())}
        if share:
            msg = {**msg, "text": "shared: " + share["title"], "share": share}
        with self.lock:
            _append(cid, msg)
            s = _load()
            s["channels"][cid]["last"] = msg["at"]
            s["channels"][cid]["request"] = False
            _save(s)
        try:
            ok = self._do(self._seal_and_send(ch, text, rid, bool(share)), 60)
        except Exception:
            ok = 0
        return {**self._view(msg), "relays_ok": ok}

    async def _seal_and_send(self, ch: dict, text: str, rid: str, share: bool = False) -> int:
        n = _n()
        everyone = ch["members"] + [self.me]
        best = 0
        for receiver in everyone:
            tags = [n.Tag.custom("rh-id", [rid])]
            if share:
                tags.append(n.Tag.custom("rh-share", ["1"]))
            if self.pseudo:
                tags.append(n.Tag.custom("rh-name", [self.pseudo]))
            if ch["name"]:
                tags.append(n.Tag.custom("subject", [ch["name"]]))
            tags += [n.Tag.public_key(n.PublicKey.parse(m)) for m in ch["members"] if m != receiver]
            wrap = await _aw(n.nip17_make_private_msg(self.keys, n.PublicKey.parse(receiver), text,
                                                      rumor_extra_tags=tags))
            out = await _aw(self.client.send_event(wrap))
            if receiver != self.me:
                best = max(best, len(out.success))
        return best

    def _apply(self, op: dict) -> None:
        """An account operation made on one of your devices."""
        with self.lock:
            s = _load()
            if op.get("op") == "contact_add" and _hex_of(op.get("hex", "")):
                s["contacts"][op["hex"]] = {"name": str(op.get("name", ""))[:40] or "friend"}
            elif op.get("op") == "group_create":
                members = sorted(m for m in op.get("members", []) if _hex_of(m))
                if members:
                    cid = channel_id(set(members) | {self.me})
                    s["channels"].setdefault(cid, {"name": str(op.get("name", ""))[:60], "members": members,
                                                   "unread": 0, "last": int(time.time()), "request": False})
            for ch in s["channels"].values():
                if all(m in s["contacts"] for m in ch["members"]):
                    ch["request"] = False
            _save(s)

    def _announce(self, op: dict) -> None:
        """Tell your other devices (sealed to yourself, kept a month)."""
        if not self.client:
            return
        n = _n()

        async def go():
            wrap = await _aw(n.nip17_make_private_msg(self.keys, self.keys.public_key(), json.dumps(op),
                                                      expiration=timedelta(days=30),
                                                      rumor_extra_tags=[n.Tag.custom("rh-op", ["1"])]))
            await _aw(self.client.send_event(wrap))
        try:
            asyncio.run_coroutine_threadsafe(go(), self.loop)
        except Exception:
            pass

    def send_share(self, cid: str, share: dict) -> dict | None:
        """A conversation, sealed for the channel: titles and messages only."""
        events = [{"type": e.get("type"), "text": str(e.get("text", ""))[:6000]}
                  for e in (share.get("events") or []) if e.get("type") in ("user", "text")]
        payload = {"rh": "share", "title": str(share.get("title", ""))[:120], "agent": str(share.get("agent", ""))[:60], "events": events}
        while len(json.dumps(payload, ensure_ascii=False)) > 40000 and payload["events"]:
            payload["events"].pop(0)                     # a sealed message holds ~64 KB: keep the latest
        return self.send(cid, json.dumps(payload, ensure_ascii=False), share=payload)

    def send_self(self, payload: dict) -> int:
        """A sealed message to yourself (your phone reads it), gone after a day."""
        if not self.ready():
            return 0
        n = _n()

        async def go():
            wrap = await _aw(n.nip17_make_private_msg(
                self.keys, self.keys.public_key(), json.dumps(payload, ensure_ascii=False),
                expiration=timedelta(days=1), rumor_extra_tags=[n.Tag.custom("rh-remote", ["1"])]))
            out = await _aw(self.client.send_event(wrap))
            self.last_refused = {str(k): v for k, v in out.failed.items()}
            return len(out.success)
        return self._do(go(), 30)

    def close(self) -> None:
        try:
            if self.client:
                self._do(_aw(self.client.disconnect()), 5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
