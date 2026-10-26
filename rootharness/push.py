"""
Notifications on your phone, with no server of ours (Web Push).

  - Your phone (the web app, added to the home screen) subscribes and gives this
    computer its push address, sealed (see remote.py).
  - When your agent needs you (a permission, a question) or finishes a long
    task, this computer sends the notification itself to Apple's or Google's
    push service, signed with its own key (VAPID) and with the content
    encrypted for your phone only (RFC 8291): the push service carries it
    without being able to read it.
  - The text stays generic ("Claude Agent needs you"): it shows on a locked
    screen, so it never contains your conversation.

The keys and subscriptions live in ~/.root-harness/push.json.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path

HOME = Path(os.environ.get("ROOT_HARNESS_HOME") or Path.home() / ".root-harness")
FILE = HOME / "push.json"
CONTACT = "https://root-harness.pages.dev"     # who sends, for the push services (a bare https origin)

on_change = lambda: None     # the window points this at the sync
_lock = threading.RLock()     # register() reads the keys while holding it


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _load() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(d, indent=1), encoding="utf-8")
    FILE.chmod(0o600)
    on_change()


def _keys() -> dict:
    """This account's VAPID key pair (P-256), made once."""
    with _lock:
        d = _load()
        if not d.get("private"):
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import serialization
            k = ec.generate_private_key(ec.SECP256R1())
            d["private"] = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()).decode()
            d["public"] = _b64u(k.public_key().public_bytes(serialization.Encoding.X962,
                                                            serialization.PublicFormat.UncompressedPoint))
            d.setdefault("subs", [])
            _save(d)
        return d


def public_key() -> str:
    """What the phone needs to subscribe (applicationServerKey)."""
    return _keys()["public"]


def register(sub: dict, device: str = "") -> bool:
    if not isinstance(sub, dict) or not str(sub.get("endpoint", "")).startswith("https://"):
        return False
    keys = sub.get("keys") or {}
    if not keys.get("p256dh") or not keys.get("auth"):
        return False
    with _lock:
        d = _keys()
        d["subs"] = [s for s in d.get("subs", []) if s["endpoint"] != sub["endpoint"]]
        d["subs"].append({"endpoint": sub["endpoint"], "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]},
                          "device": device[:60], "added": int(time.time())})
        _save(d)
    return True


def count() -> int:
    return len(_load().get("subs", []))


def notify(title: str, body: str, tag: str = "root-harness", urgent: bool = False) -> int:
    """Send to every subscribed phone. Returns how many accepted it."""
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid
    d = _keys()
    signer = Vapid.from_pem(d["private"].encode())
    payload = json.dumps({"title": title[:80], "body": body[:140], "tag": tag})
    ok, gone = 0, []
    for s in list(d.get("subs", [])):
        try:
            webpush(subscription_info={"endpoint": s["endpoint"], "keys": s["keys"]}, data=payload,
                    vapid_private_key=signer, vapid_claims={"sub": CONTACT}, ttl=3600,
                    headers={"Urgency": "high" if urgent else "normal"}, timeout=10)
            ok += 1
        except WebPushException as e:
            if getattr(e, "response", None) is not None and e.response.status_code in (404, 410):
                gone.append(s["endpoint"])          # that phone unsubscribed: forget it
        except Exception:
            pass
    if gone:
        with _lock:
            d = _load()
            d["subs"] = [s for s in d.get("subs", []) if s["endpoint"] not in gone]
            _save(d)
    return ok


def raw() -> dict:
    return _load()


def merge(remote: dict) -> None:
    """Another computer of yours: same key, so your phones' subscriptions work from both."""
    with _lock:
        d = _load()
        if not d.get("private"):
            d = {"private": remote.get("private"), "public": remote.get("public"), "subs": []}
        if d["private"] != remote.get("private"):
            return                          # subscriptions are bound to a key: keep this one's
        have = {s["endpoint"] for s in d.get("subs", [])}
        d["subs"] = d.get("subs", []) + [s for s in remote.get("subs", []) if s.get("endpoint") not in have]
        _save(d)


def notify_later(title: str, body: str, tag: str = "root-harness", urgent: bool = False) -> None:
    if count():
        threading.Thread(target=notify, args=(title, body, tag, urgent), daemon=True).start()
