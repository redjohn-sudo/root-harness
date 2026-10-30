"""
Link a phone with a QR code, instead of typing a pseudo and a password.

  1. The computer makes a one-time key and shows it in a QR code (a link to the
     phone app). It is not a secret.
  2. The phone, opened by its camera, makes its own one-time key and answers,
     sealed to the computer's key, through the relays.
  3. Both screens show the same 6-digit code, computed from the two one-time
     keys. If someone stood in between, the codes would differ: you compare,
     then approve on the computer.
  4. The computer sends your identity sealed to the phone's one-time key; the
     phone locks it with a code of your choice. The one-time keys are dropped.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import threading
import time
from datetime import timedelta
from typing import Callable

RELAYS = ["wss://nos.lol", "wss://relay.primal.net", "wss://relay.snort.social"]
LIFETIME = 300          # seconds a QR code stays valid


def _n():
    import nostr_sdk
    return nostr_sdk


async def _aw(x):
    return await x if inspect.isawaitable(x) else x


def code(computer_hex: str, phone_hex: str) -> str:
    """The 6 digits both screens show (the same computation on the phone)."""
    h = hashlib.sha256(bytes.fromhex(computer_hex) + bytes.fromhex(phone_hex)).digest()
    n = int.from_bytes(h[:4], "big") % 1_000_000
    return f"{n:06d}"


class Pairing:
    def __init__(self, identity, pseudo: str, on_event: Callable[[dict], None]):
        n = _n()
        self.identity, self.pseudo, self.on_event = identity, pseudo, on_event
        self.eph = n.Keys.generate()
        self.phone: str | None = None
        self.started = time.time()
        self.done = False
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.client = None
        asyncio.run_coroutine_threadsafe(self._listen(), self.loop)

    @property
    def token(self) -> str:
        return self.eph.public_key().to_bech32()

    async def _listen(self) -> None:
        n = _n()
        self.client = n.ClientBuilder().build()
        for r in RELAYS:
            await _aw(self.client.add_relay(n.RelayUrl.parse(r)))
        await _aw(self.client.connect(and_wait=timedelta(seconds=6)))
        f = n.Filter().kind(n.Kind(1059)).pubkey(self.eph.public_key()).since(
            n.Timestamp.from_secs(int(self.started) - 3 * 86400))
        await _aw(self.client.subscribe(n.ReqTarget.auto([f])))
        stream = await _aw(self.client.notifications())
        while not self.done:
            note = await _aw(stream.next())
            if note is None:
                break
            if not note.is_new_event() or time.time() - self.started > LIFETIME:
                continue
            try:
                gift = await _aw(n.UnwrappedGift.from_gift_wrap(self.eph, note.event))
                msg = json.loads(gift.rumor().content())
            except Exception:
                continue
            if msg.get("op") == "pair-hello" and self.phone is None and gift.rumor().created_at().as_secs() >= self.started - 30:
                self.phone = gift.sender().to_hex()
                self.on_event({"type": "pair_code", "code": code(self.eph.public_key().to_hex(), self.phone)})

    def approve(self) -> bool:
        """You compared the codes: send the identity, sealed for that phone only."""
        if not self.phone or self.done or time.time() - self.started > LIFETIME:
            return False
        n = _n()
        payload = json.dumps({"op": "pair-key", "key": self.identity.secret_key().to_bech32(), "pseudo": self.pseudo})

        async def go():
            wrap = await _aw(n.nip17_make_private_msg(self.eph, n.PublicKey.parse(self.phone), payload,
                                                      expiration=timedelta(days=3),   # wraps are back-dated up to 2 days: less would be born expired
                                                      rumor_extra_tags=[n.Tag.custom("rh-pair", ["1"])]))
            out = await _aw(self.client.send_event(wrap))
            return len(out.success)
        try:
            ok = asyncio.run_coroutine_threadsafe(go(), self.loop).result(30) > 0
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            ok = False
        if ok:
            self.close()
        return ok

    def close(self) -> None:
        self.done = True
        try:
            if self.client:
                asyncio.run_coroutine_threadsafe(_aw(self.client.disconnect()), self.loop).result(5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
