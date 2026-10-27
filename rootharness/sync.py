"""
Your root-harness account on every machine: the whole memory of the account,
sealed so that only you can read it, kept on public Nostr relays.

What travels: settings (brain, models, efforts, modes, background), your
conversations and folders, the history needed to continue them, your
contacts and encrypted channels, your API keys. All of it.

How it stays private:
  - each piece is sealed to yourself (NIP-44) with your identity key, which
    only exists unlocked on your machines;
  - pieces are app-data events (NIP-78) whose labels are random-looking
    (HMAC of the name with a key derived from yours): relays cannot tell a
    conversation from a contact list, nor read a title;
  - signing in elsewhere goes through the login key of account.py, so the
    relays never see your pseudo or your password.

What relays still see: that your public ID stores some sealed pieces, their
sizes and when they change. Free relays promise no storage, so root-harness
publishes to several and republishes what changed; keep one machine around
until the other has synced.

Claude Code sessions themselves live in ~/.claude on the machine that ran them:
on another machine the conversation shows in full, and Claude continues with
that history given as context.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import inspect
import json
import os
import subprocess
import threading
import time
import zlib
from datetime import timedelta
from pathlib import Path
from typing import Callable

from . import account, conversations, glossary, push, network

HOME = Path(os.environ.get("ROOT_HARNESS_HOME") or Path.home() / ".root-harness")
STATE = HOME / "sync.json"
RELAYS = ["wss://relay.damus.io", "wss://nos.lol", "wss://relay.primal.net"]
KIND = 30078            # NIP-78, replaceable per (author, label)
LOGIN_LABEL = "root-harness-login"
CHUNK = 30000           # characters per sealed piece (NIP-44 stops near 65 000)
TRIM = 4000             # long tool outputs are cut to this many characters
PACE = 0.6              # seconds between two sends: free relays ban bursts


def _n():
    import nostr_sdk
    return nostr_sdk


async def _aw(x):
    return await x if inspect.isawaitable(x) else x


def _digest(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


async def _client():
    n = _n()
    c = n.ClientBuilder().build()
    for r in RELAYS:
        await _aw(c.add_relay(n.RelayUrl.parse(r)))
    await _aw(c.connect(and_wait=timedelta(seconds=6)))
    return c


async def _fetch(c, f) -> list:
    evs = await _aw(c.fetch_events(_n().ReqTarget.auto([f]), timeout=timedelta(seconds=10)))
    return evs.to_vec() if hasattr(evs, "to_vec") else list(evs)


# -- signing in elsewhere: the locked identity, found by pseudo + password ----

async def publish_login(pseudo: str, password: str, locked_key: str) -> int:
    n = _n()
    lk = await asyncio.to_thread(account.login_keys, pseudo, password)
    sealed = lk.nip44_encrypt(lk.public_key(), json.dumps({"locked_key": locked_key, "pseudo": pseudo}))
    ev = n.EventBuilder(n.Kind(KIND), sealed).tags([n.Tag.identifier(LOGIN_LABEL)]).finalize(lk)
    c = await _client()
    try:
        out = await _aw(c.send_event(ev))
        return len(out.success)
    finally:
        await _aw(c.disconnect())


async def fetch_login(pseudo: str, password: str) -> dict | None:
    n = _n()
    lk = await asyncio.to_thread(account.login_keys, pseudo, password)
    c = await _client()
    try:
        evs = await _fetch(c, n.Filter().kind(n.Kind(KIND)).author(lk.public_key()).identifier(LOGIN_LABEL))
    finally:
        await _aw(c.disconnect())
    for ev in sorted(evs, key=lambda e: -e.created_at().as_secs()):
        try:
            return json.loads(lk.nip44_decrypt(lk.public_key(), ev.content()))
        except Exception:
            continue
    return None


# -- the memory of the account ---------------------------------------------------

def _trim_events(events: list) -> list:
    out = []
    for e in events:
        if e.get("type") == "result" and len(e.get("text") or "") > TRIM:
            e = {**e, "text": e["text"][:TRIM] + "\n[...]"}
        out.append(e)
    return out


def _trim_messages(msgs: list) -> list:
    out = []
    for m in msgs or []:
        if m.get("role") == "tool" and isinstance(m.get("content"), str) and len(m["content"]) > TRIM:
            m = {**m, "content": m["content"][:TRIM] + "\n[...]"}
        out.append(m)
    return out


def _background() -> dict | None:
    """The background picture, made small enough to travel (macOS sips)."""
    ui = Path(__file__).parent / "ui"
    pic = next(iter(ui.glob("background.local.*")), None)
    if not pic:
        return None
    small = HOME / "background.sync.jpg"
    if not small.exists() or small.stat().st_mtime < pic.stat().st_mtime:
        try:
            subprocess.run(["sips", "-Z", "1600", "-s", "format", "jpeg", "-s", "formatOptions", "70",
                            str(pic), "--out", str(small)], capture_output=True, timeout=30, check=True)
        except (OSError, subprocess.SubprocessError):
            return None
    return {"ext": ".jpg", "data": base64.b64encode(small.read_bytes()).decode()}


def local_items() -> dict:
    """Everything that makes the account, by name."""
    items = {}
    settings = _read(HOME / "settings.json", {})
    items["settings"] = {k: v for k, v in settings.items() if k != "image"} | {"has_image": bool(settings.get("image"))}
    bg = _background() if settings.get("image") else None
    if bg:
        items["background"] = bg
    index = conversations.all_listed()
    items["index"] = index
    for cid in index["conversations"]:
        log = conversations.read_log(cid)
        if log.get("events") or log.get("api_messages"):
            items["conv:" + cid] = {"events": _trim_events(log.get("events", [])),
                                    "api_messages": _trim_messages(log.get("api_messages"))}
    ch = _read(HOME / "channels.json", None)
    if ch:
        items["channels"] = {k: ch.get(k) for k in ("contacts", "channels", "pseudos", "relays")}
        for cid in ch.get("channels", {}):
            log = _read(HOME / "channels" / f"{cid}.json", [])
            if log:
                items["chan:" + cid] = log
    g = glossary.raw()
    if g["terms"] or g["hidden"] or g["auto"]:
        items["glossary"] = g
    p = push.raw()
    if p.get("private"):
        items["push"] = p
    net = network.raw()
    if net["profile"] or net["mine"]["reactions"] or net["mine"]["reposts"] or net["blocked"]:
        items["network"] = net
    env = HOME / ".env"
    if env.exists():
        items["keys"] = env.read_text(encoding="utf-8")
    return items


def _merge(name: str, remote) -> None:
    """Bring a piece from the relays into this machine, without losing local work."""
    if name == "settings":
        local = _read(HOME / "settings.json", {})
        merged = {**{k: v for k, v in remote.items() if k != "has_image"}, **local}
        _write(HOME / "settings.json", merged)
    elif name == "background":
        ui = Path(__file__).parent / "ui"
        if not any(ui.glob("background.local.*")):
            (ui / f"background.local{remote['ext']}").write_bytes(base64.b64decode(remote["data"]))
            st = _read(HOME / "settings.json", {})
            st["image"] = f"background.local{remote['ext']}"
            _write(HOME / "settings.json", st)
    elif name == "index":
        conversations.merge_index(remote)
    elif name.startswith("conv:"):
        cid = name[5:]
        local = conversations.read_log(cid)
        if len(remote.get("events", [])) >= len(local.get("events", [])):
            conversations.write_log(cid, {k: v for k, v in remote.items() if v})
    elif name == "channels":
        local = _read(HOME / "channels.json", {})
        for key in ("contacts", "pseudos"):
            local[key] = {**(remote.get(key) or {}), **(local.get(key) or {})}
        chans = remote.get("channels") or {}
        chans.update(local.get("channels") or {})
        local["channels"] = chans
        local.setdefault("relays", remote.get("relays"))
        local.setdefault("seen", [])
        _write(HOME / "channels.json", local)
    elif name.startswith("chan:"):
        path = HOME / "channels" / f"{name[5:]}.json"
        log = {m["rid"]: m for m in _read(path, [])}
        for m in remote:
            log.setdefault(m["rid"], m)
        _write(path, sorted(log.values(), key=lambda m: m["at"]))
    elif name == "glossary":
        glossary.merge(remote)
    elif name == "push":
        push.merge(remote)
    elif name == "network":
        network.merge(remote)
    elif name == "keys":
        env = HOME / ".env"
        have = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
        names = {l.split("=", 1)[0] for l in have if "=" in l}
        add = [l for l in remote.splitlines() if "=" in l and l.split("=", 1)[0] not in names]
        if add:
            env.write_text("\n".join(have + add) + "\n", encoding="utf-8")
            env.chmod(0o600)


class Sync:
    """Keeps this machine and the relays in step, on its own loop."""

    def __init__(self, keys, on_event: Callable[[dict], None]):
        self.keys = keys
        self.on_event = on_event
        secret = bytes.fromhex(keys.secret_key().to_hex())
        self.label_key = hashlib.sha256(b"root-harness/sync/labels/v1" + secret).digest()
        self.client = None
        self._connecting = None
        self.lock = threading.Lock()
        self._dirty = threading.Event()
        self.last = {"pushed": None, "pulled": None, "error": None}
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        asyncio.run_coroutine_threadsafe(self._run(), self.loop)

    def _label(self, name: str) -> str:
        return hmac.new(self.label_key, name.encode(), hashlib.sha256).hexdigest()[:40]

    def _seal(self, text: str) -> str:
        return self.keys.nip44_encrypt(self.keys.public_key(), text)

    def _open(self, sealed: str) -> str:
        return self.keys.nip44_decrypt(self.keys.public_key(), sealed)

    def dirty(self) -> None:
        """Something changed here: send it soon."""
        self._dirty.set()

    # -- the loop: pull at start, then push what changes, pull now and then ----

    async def _connected(self):
        """One connection, made once, whoever asks first."""
        if self._connecting is None:
            self._connecting = asyncio.ensure_future(_client())
        self.client = await asyncio.shield(self._connecting)
        return self.client

    async def _run(self) -> None:
        try:
            await self._connected()
            changed = await self.pull()
            self.on_event({"type": "synced", "changed": changed})
            await self.push()
        except Exception as e:
            self.last["error"] = f"{type(e).__name__}: {e}"
        tick = 0
        while True:
            await asyncio.sleep(5)
            tick += 5
            try:
                if self._dirty.is_set():
                    await asyncio.sleep(10)       # let a burst of changes settle
                    self._dirty.clear()
                    await self.push()
                if tick >= 180:                   # what the other machines did
                    tick = 0
                    if await self.pull():
                        self.on_event({"type": "synced", "changed": True})
            except Exception as e:
                self.last["error"] = f"{type(e).__name__}: {e}"

    async def _publish(self, label: str, text: str) -> int:
        n = _n()
        await self._connected()
        ev = n.EventBuilder(n.Kind(KIND), self._seal(text)).tags([n.Tag.identifier(label)]).finalize(self.keys)
        out = await _aw(self.client.send_event(ev))
        if out.failed:
            self.last["refused"] = {str(k): v for k, v in out.failed.items()}
        await asyncio.sleep(PACE)
        return len(out.success)

    async def push(self) -> int:
        """Send the pieces that changed since last time, then the list of pieces."""
        state = _read(STATE, {"pushed": {}})
        items = await asyncio.to_thread(local_items)
        manifest = {"items": {}, "at": int(time.time())}
        sent = 0
        for name, data in items.items():
            text = base64.b64encode(zlib.compress(json.dumps(data, ensure_ascii=False).encode(), 9)).decode()
            digest = _digest(data)
            parts = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)] or [""]
            manifest["items"][name] = {"h": digest, "n": len(parts)}
            if state["pushed"].get(name) == digest:
                continue
            accepted = [await self._publish(self._label(f"{name}#{i}"), part) for i, part in enumerate(parts)]
            if min(accepted) == 0:
                missing = True                 # a relay said no: try again next round
                continue
            state["pushed"][name] = digest
            sent += 1
        missing = any(state["pushed"].get(k) != v["h"] for k, v in manifest["items"].items())
        if not missing and (sent or state.get("manifest") != _digest(manifest["items"])):
            ok = await self._publish(self._label("manifest"), json.dumps(manifest))
            if ok:
                state["manifest"] = _digest(manifest["items"])
            self.last["relays"] = ok
        if missing:
            self._dirty.set()
        _write(STATE, state)
        self.last["pushed"] = int(time.time())
        return sent

    async def pull(self) -> bool:
        """Fetch the list of pieces; bring in those this machine does not have."""
        n = _n()
        await self._connected()
        me = self.keys.public_key()
        evs = await _fetch(self.client, n.Filter().kind(n.Kind(KIND)).author(me).identifier(self._label("manifest")))
        if not evs:
            self.last["pulled"] = int(time.time())
            return False
        manifest = json.loads(self._open(max(evs, key=lambda e: e.created_at().as_secs()).content()))
        state = _read(STATE, {"pushed": {}})
        local = await asyncio.to_thread(local_items)
        changed = False
        for name, meta in manifest["items"].items():
            if name in local and _digest(local[name]) == meta["h"]:
                continue
            if state["pushed"].get(name) == meta["h"]:
                continue                       # we sent this one ourselves
            labels = [self._label(f"{name}#{i}") for i in range(meta["n"])]
            got = {}
            for ev in await _fetch(self.client, n.Filter().kind(n.Kind(KIND)).author(me).identifiers(labels)):
                d = next((t.content() for t in ev.tags() if t.kind() == "d"), "")
                if d in labels and (d not in got or ev.created_at().as_secs() > got[d][0]):
                    got[d] = (ev.created_at().as_secs(), ev)
            if len(got) < len(labels):
                continue                       # a piece is missing on these relays: next time
            try:
                text = "".join(self._open(got[l][1].content()) for l in labels)
                data = json.loads(zlib.decompress(base64.b64decode(text)))
                if _digest(data) != meta["h"]:
                    continue                   # pieces from two different versions: next time
            except Exception:
                continue
            with self.lock:
                await asyncio.to_thread(_merge, name, data)
            state["pushed"][name] = meta["h"]
            changed = True
        _write(STATE, state)
        self.last["pulled"] = int(time.time())
        return changed

    def status(self) -> dict:
        return dict(self.last)

    def push_now(self, timeout=120) -> int:
        return asyncio.run_coroutine_threadsafe(self.push(), self.loop).result(timeout)

    def close(self) -> None:
        try:
            if self.client:
                asyncio.run_coroutine_threadsafe(_aw(self.client.disconnect()), self.loop).result(5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
