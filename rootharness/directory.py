"""
Your ID, to give to friends and colleagues: your pseudo plus a code computed
from your key, like  vincent#k7f2qa9m.

  - Two people can both be "vincent"; their codes differ, so the full ID is
    unique. The code comes from the key, so nobody can take yours: they would
    need a key whose hash starts the same way (about 10^12 tries).
  - If you agree to be findable, root-harness publishes a small public card
    (your ID and your public key) on the relays. Adding you by your ID looks
    for that card and checks that the code matches the key it names; a card
    that does not match is ignored.
  - Without the card, friends can still add you with your QR code or your
    long public key.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import re
import unicodedata
from datetime import timedelta

RELAYS = ["wss://relay.damus.io", "wss://nos.lol", "wss://relay.primal.net"]
KIND = 30078
PREFIX = "rh-handle:"
CODE = 8


def _n():
    import nostr_sdk
    return nostr_sdk


async def _aw(x):
    return await x if inspect.isawaitable(x) else x


def code(pubkey_hex: str) -> str:
    """8 characters (base32) from the public key: 40 bits that cannot be chosen."""
    return base64.b32encode(hashlib.sha256(bytes.fromhex(pubkey_hex)).digest()).decode().lower()[:CODE]


def slug(pseudo: str) -> str:
    """The pseudo as it goes in an ID: lowercase, no accents, no spaces."""
    s = unicodedata.normalize("NFKD", pseudo or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9._-]+", "", " ".join(s.split()).replace(" ", "."))
    return s[:24].strip("._-") or "friend"


def handle(pseudo: str, pubkey_hex: str) -> str:
    return f"{slug(pseudo)}#{code(pubkey_hex)}"


def parse(text: str) -> tuple[str, str] | None:
    """'vincent#k7f2qa9m' -> ('vincent', 'k7f2qa9m'), or None."""
    m = re.fullmatch(r"\s*([a-z0-9._-]{1,24})#([a-z2-7]{%d})\s*" % CODE, (text or "").lower())
    return (m.group(1), m.group(2)) if m else None


async def _client():
    n = _n()
    c = n.ClientBuilder().build()
    for r in RELAYS:
        await _aw(c.add_relay(n.RelayUrl.parse(r)))
    await _aw(c.connect(and_wait=timedelta(seconds=6)))
    return c


async def publish(keys, pseudo: str) -> int:
    """Your public card: your ID points to your public key."""
    n = _n()
    h = handle(pseudo, keys.public_key().to_hex())
    ev = n.EventBuilder(n.Kind(KIND), json.dumps({"id": h, "pseudo": pseudo})).tags(
        [n.Tag.identifier(PREFIX + h)]).finalize(keys)
    c = await _client()
    try:
        out = await _aw(c.send_event(ev))
        return len(out.success)
    finally:
        await _aw(c.disconnect())


async def withdraw(keys, pseudo: str) -> None:
    """Stop being findable: the card is replaced by an empty one."""
    n = _n()
    h = handle(pseudo, keys.public_key().to_hex())
    ev = n.EventBuilder(n.Kind(KIND), "").tags([n.Tag.identifier(PREFIX + h)]).finalize(keys)
    c = await _client()
    try:
        await _aw(c.send_event(ev))
    finally:
        await _aw(c.disconnect())


async def lookup(text: str) -> dict | None:
    """Find someone by ID. Only a card whose key matches the code counts."""
    p = parse(text)
    if not p:
        return None
    name, want = p
    n = _n()
    c = await _client()
    try:
        evs = await _aw(c.fetch_events(n.ReqTarget.auto([n.Filter().kind(n.Kind(KIND)).identifier(PREFIX + f"{name}#{want}")]),
                                       timeout=timedelta(seconds=8)))
        evs = evs.to_vec() if hasattr(evs, "to_vec") else list(evs)
    finally:
        await _aw(c.disconnect())
    for ev in sorted(evs, key=lambda e: -e.created_at().as_secs()):
        pub = ev.author().to_hex()
        if code(pub) != want or not ev.content():
            continue                                  # an impostor, or a withdrawn card
        try:
            card = json.loads(ev.content())
        except ValueError:
            continue
        return {"hex": pub, "npub": ev.author().to_bech32(), "pseudo": str(card.get("pseudo", name))[:32],
                "id": f"{name}#{want}"}
    return None
