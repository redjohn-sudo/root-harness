"""
Your root-harness account: a pseudo and a password, on your machine only.

There is no server and no sign-up anywhere. The "account" is your identity key
(the one your encrypted channels use), locked with your password following
NIP-49 (scrypt, then XChaCha20-Poly1305). ~/.root-harness/account.json keeps
the locked key (ncryptsec1...), your pseudo and your public ID; never the
password, never the unlocked key.

"Stay signed in" keeps the unlocked key in the system keychain so root-harness
opens without asking. Off, the unlocked key only lives in memory, after you
type your password.

A forgotten password cannot be recovered (that is the point of it). You can
start a new account; your contacts will then need your new ID.

Signing in on another machine (see sync.py): your pseudo and password, through
a slow function (scrypt, 256 MB, ~0.4 s), give a "login key". The locked
identity key is published on relays under that login key, sealed to it. So
the new machine finds it with nothing but your pseudo and password, nobody
can link it to your public ID, and each password guess costs an attacker two
slow functions and the right pseudo.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

HOME = Path(os.environ.get("ROOT_HARNESS_HOME") or Path.home() / ".root-harness")
ACCOUNT = HOME / "account.json"
KEYCHAIN = ("root-harness", "nostr-secret-key")
MIN_PASSWORD = 10     # the locked key is published for sync: no short passwords


def _n():
    import nostr_sdk
    return nostr_sdk


def _keyring():
    import keyring
    return keyring


def _load() -> dict | None:
    try:
        return json.loads(ACCOUNT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(acc: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = ACCOUNT.with_suffix(".tmp")
    tmp.write_text(json.dumps(acc, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(ACCOUNT)


def _clean_pseudo(pseudo: str) -> str:
    return " ".join((pseudo or "").split())[:32]


def norm_pseudo(pseudo: str) -> str:
    return _clean_pseudo(pseudo).lower()


def login_keys(pseudo: str, password: str):
    """The same pseudo + password always give the same login key."""
    seed = hashlib.scrypt(password.encode(), salt=b"root-harness/login/v1/" + norm_pseudo(pseudo).encode(),
                          n=2 ** 18, r=8, p=1, maxmem=600 * 1024 * 1024, dklen=32)
    n = _n()
    return n.Keys.parse(n.SecretKey.from_bytes(seed).to_hex())


def locked_key() -> str | None:
    acc = _load()
    return acc["locked_key"] if acc else None


def restore(pseudo: str, locked: str, password: str):
    """Signing in on a new machine: keep the identity found on the relays."""
    n = _n()
    try:
        secret = n.EncryptedSecretKey.from_bech32(locked).decrypt(password)
    except Exception:
        return None
    keys = n.Keys.parse(secret.to_bech32())
    _save({"pseudo": _clean_pseudo(pseudo), "npub": keys.public_key().to_bech32(),
           "locked_key": locked, "stay": False, "sync": True})
    return keys


def state() -> dict:
    acc = _load()
    if not acc:
        return {"exists": False}
    return {"exists": True, "pseudo": acc["pseudo"], "npub": acc["npub"], "stay": acc.get("stay", False),
            "sync": acc.get("sync", True)}


def set_sync(on: bool) -> None:
    acc = _load()
    if acc:
        acc["sync"] = bool(on)
        _save(acc)


def create(pseudo: str, password: str, again: str, sync: bool = True):
    """Returns (keys, None) or (None, reason)."""
    n = _n()
    pseudo = _clean_pseudo(pseudo)
    if not pseudo:
        return None, "Choose a pseudo."
    if len(password) < MIN_PASSWORD:
        return None, f"Your password needs at least {MIN_PASSWORD} characters."
    if password != again:
        return None, "The two passwords are different."
    # keep an identity that already exists on this Mac, so your ID does not change
    old = _keyring().get_password(*KEYCHAIN)
    keys = n.Keys.parse(old) if old else n.Keys.generate()
    _save({"pseudo": pseudo, "npub": keys.public_key().to_bech32(),
           "locked_key": keys.secret_key().encrypt(password).to_bech32(), "stay": False, "sync": bool(sync)})
    _forget_in_keychain()          # off by default: you choose in Settings
    return keys, None


def unlock(password: str):
    acc = _load()
    if not acc:
        return None
    n = _n()
    try:
        secret = n.EncryptedSecretKey.from_bech32(acc["locked_key"]).decrypt(password)
    except Exception:
        return None
    return n.Keys.parse(secret.to_bech32())


def auto():
    """Signed in without a password, when you chose to stay signed in."""
    acc = _load()
    if not acc or not acc.get("stay"):
        return None
    secret = _keyring().get_password(*KEYCHAIN)
    if not secret:
        return None
    keys = _n().Keys.parse(secret)
    return keys if keys.public_key().to_bech32() == acc["npub"] else None


def set_stay(on: bool, keys) -> bool:
    acc = _load()
    if not acc or keys is None:
        return False
    if on:
        _keyring().set_password(*KEYCHAIN, keys.secret_key().to_bech32())
    else:
        _forget_in_keychain()
    acc["stay"] = bool(on)
    _save(acc)
    return True


def change_password(old: str, new: str, again: str) -> str | None:
    """None when done, or the reason it was refused."""
    keys = unlock(old)
    if keys is None:
        return "Your current password is not right."
    if len(new) < MIN_PASSWORD:
        return f"Your new password needs at least {MIN_PASSWORD} characters."
    if new != again:
        return "The two new passwords are different."
    acc = _load()
    acc["locked_key"] = keys.secret_key().encrypt(new).to_bech32()
    _save(acc)
    return None


def set_pseudo(pseudo: str) -> bool:
    acc, pseudo = _load(), _clean_pseudo(pseudo)
    if not acc or not pseudo:
        return False
    acc["pseudo"] = pseudo
    _save(acc)
    return True


def reset() -> None:
    """Forgotten password: start over with a new identity. The old channels
    belonged to the old identity, so they go too."""
    _forget_in_keychain()
    ACCOUNT.unlink(missing_ok=True)
    (HOME / "channels.json").unlink(missing_ok=True)
    folder = HOME / "channels"
    if folder.is_dir():
        for f in folder.glob("*.json"):
            f.unlink()


def _forget_in_keychain() -> None:
    try:
        _keyring().delete_password(*KEYCHAIN)
    except Exception:
        pass
