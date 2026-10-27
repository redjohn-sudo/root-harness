"""
The network: what people build with their agents, in the open.

  - Your profile, your posts, your replies, reposts and reactions, your badges
    and the communities you post in are plain Nostr events, signed with the
    same key as your account and kept by public relays. No server of ours, and
    any Nostr app can read them too.
  - A post made in root-harness carries the tag #root-harness: the "for you"
    feed is everyone posting from root-harness, plus your friends wherever
    they post from.
  - Pictures and videos cannot live on relays: they are uploaded to a public
    media host (NIP-96, signed with your key) and the post keeps the link.
  - Badges follow NIP-58: a definition, an award, and the ones you pin on your
    profile. Automatic badges (first post, 7 days in a row...) are awarded by
    your own root-harness, so they are shown as "self-certified"; a badge made
    by someone else for an event is shown with that person's name.
  - How active you are comes from your own use of root-harness (the days you
    worked with your agents), published by you in your profile extras.

Nothing here is encrypted: everything in this file is meant to be public.
Friends and channels (channels.py) stay sealed as before.

Local copies live in ~/.root-harness/network/ (your profile extras, your work
list, the ids of your own reactions so you can take them back).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import mimetypes
import os
import re
import threading
import time
import urllib.request
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Callable

from . import directory

HOME = Path(os.environ.get("ROOT_HARNESS_HOME") or Path.home() / ".root-harness")
DIR = HOME / "network"
PROFILE = DIR / "profile.json"        # your extras: school, role, state, work list, pinned badges
MINE = DIR / "mine.json"              # ids of your own reactions and reposts, to take them back
NOTIFS = DIR / "notifications.json"   # when you last looked, followers already known, what was already pushed
RELAYS = ["wss://relay.damus.io", "wss://nos.lol", "wss://relay.primal.net"]
TAG = "root-harness"                  # on every post made here: the "for you" feed is this tag
EXTRAS = "rh-profile"                 # kind 30078 identifier of your profile extras
AT = "rh-at:"                         # kind 30078 identifier of an @name claim: the first claim wins
MEDIA_HOST = "https://nostr.build/api/v2/nip96/upload"
MEDIA_MAX = 20 * 1024 * 1024
STATES = ("etudie", "travaille", "cherche")
LEVELS = ((20, "actively active"), (8, "very active"), (1, "active"))

K_PROFILE, K_POST, K_FOLLOWS, K_REPOST, K_REACTION, K_AWARD, K_DELETE = 0, 1, 3, 6, 7, 8, 5
K_PINNED, K_BADGE, K_COMMUNITY, K_APPDATA, K_AUTH = 30008, 30009, 34550, 30078, 27235

on_change = lambda: None     # the window points this at the sync


def _n():
    import nostr_sdk
    return nostr_sdk


async def _aw(x):
    return await x if inspect.isawaitable(x) else x


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, data) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    on_change()


def at_norm(name: str) -> str:
    """@Root_42 -> root_42 ; '' when it cannot be an @ (3 to 20 letters, digits or _)."""
    n = (name or "").strip().lstrip("@").lower()
    return n if re.fullmatch(r"[a-z0-9_]{3,20}", n) else ""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", (text or "").lower()).strip("-")[:40]


def _work_item(w: dict) -> dict:
    """A work line from somebody's extras, kept to what the page shows; only web links are kept."""
    url = str(w.get("url") or "")
    return {"kind": w.get("kind") if w.get("kind") in ("project", "hackathon", "progress") else "project",
            "title": str(w.get("title", ""))[:60], "text": str(w.get("text", ""))[:200], "when": str(w.get("when", ""))[:24],
            "live": bool(w.get("live")), "url": url[:200] if re.match(r"https?://", url) else "",
            "image": str(w.get("image") or "")[:300] if str(w.get("image") or "").startswith("https://") else ""}


def _tags(ev) -> list[list[str]]:
    return [t.to_vec() for t in ev.tags()]


def _first(tags: list[list[str]], name: str, default: str = "") -> str:
    return next((t[1] for t in tags if len(t) > 1 and t[0] == name), default)


# -- how active you are, from your own days with your agents ---------------------------

def activity(days: int = 30) -> dict:
    """Distinct days (out of the last 30) with a conversation touched."""
    from . import conversations
    now = time.time()
    seen = set()
    for c in conversations.all_listed()["conversations"].values():
        at = (c.get("updated") or c.get("created") or 0) / 1000
        if now - at < days * 86400:
            seen.add(int(at // 86400))
    n = len(seen)
    level = 3 if n >= LEVELS[0][0] else 2 if n >= LEVELS[1][0] else 1 if n >= LEVELS[2][0] else 0
    return {"days": n, "level": level, "label": level_label(level)}


def level_label(level: int) -> str:
    return {3: "actively active", 2: "very active", 1: "active"}.get(int(level or 0), "")


# -- your profile, locally ------------------------------------------------------------------

def profile_local() -> dict:
    p = _read(PROFILE, {})
    p.setdefault("name", "")               # first and last name, optional
    p.setdefault("show", "pseudo")         # pseudo | name | both
    p.setdefault("about", "")
    p.setdefault("picture", "")            # a URL (uploaded) or a small data URL
    p.setdefault("banner", "")
    p.setdefault("school", "")
    p.setdefault("role", "")
    p.setdefault("state", "etudie")        # etudie | travaille | cherche
    p.setdefault("work", [])               # [{id, kind: project|hackathon|progress, title, text, when, live}]
    p.setdefault("pinned", [])             # badge coordinates (30009:<issuer>:<d>)
    p.setdefault("communities", [])        # slugs you joined
    p.setdefault("at", "")                 # your @, once claimed (claim_at)
    return p


def profile_set(fields: dict) -> dict:
    p = profile_local()
    for k in ("name", "about", "picture", "banner", "school", "role"):
        if k in fields:
            p[k] = str(fields[k] or "")[: 2000 if k in ("picture", "banner") else 160]
    if fields.get("show") in ("pseudo", "name", "both"):
        p["show"] = fields["show"]
    if fields.get("state") in STATES:
        p["state"] = fields["state"]
    if isinstance(fields.get("work"), list):
        p["work"] = [{"id": str(w.get("id") or uuid.uuid4().hex[:8]), "kind": w.get("kind") if w.get("kind") in ("project", "hackathon", "progress") else "project",
                      "title": str(w.get("title", ""))[:60], "text": str(w.get("text", ""))[:200], "when": str(w.get("when", ""))[:24],
                      "live": bool(w.get("live")), "url": str(w.get("url", ""))[:200],
                      "image": str(w.get("image") or "")[:300] if str(w.get("image") or "").startswith("https://") else ""}
                     for w in fields["work"] if isinstance(w, dict) and w.get("title")][:12]
    if isinstance(fields.get("pinned"), list):
        p["pinned"] = [str(a) for a in fields["pinned"] if isinstance(a, str) and a.startswith(f"{K_BADGE}:")][:8]
    if isinstance(fields.get("communities"), list):
        p["communities"] = sorted({slug(c) for c in fields["communities"] if slug(c)})[:30]
    _write(PROFILE, p)
    return p


def github_work(limit: int = 8) -> list[dict]:
    """Your own public repositories, newest activity first (through gh, signed in for vibe code)."""
    import subprocess
    try:
        login = json.loads(subprocess.run(["gh", "api", "user"], capture_output=True, text=True, timeout=20).stdout)["login"]
        repos = json.loads(subprocess.run(["gh", "api", f"users/{login}/repos?sort=pushed&per_page=30&type=owner"],
                                          capture_output=True, text=True, timeout=30).stdout)
    except Exception:
        return []
    out = []
    for r in repos if isinstance(repos, list) else []:
        if r.get("fork") or r.get("archived") or r.get("private") or not r.get("name") or r["name"].lower() == login.lower():
            continue                                    # forks, archives, and the profile README repository: not your work
        when = str(r.get("pushed_at") or "")[:7]
        out.append({"kind": "project", "title": r["name"][:60], "text": " ".join((r.get("description") or "").split())[:200],
                    "when": when, "live": False, "url": r.get("html_url", "")})
        if len(out) >= limit:
            break
    return out


def github_showcase() -> list[dict]:
    """The demos on your GitHub profile page (the <login>/<login> README): a title, a picture or GIF, a caption."""
    import html
    import subprocess
    try:
        login = json.loads(subprocess.run(["gh", "api", "user"], capture_output=True, text=True, timeout=20).stdout)["login"]
        raw = subprocess.run(["gh", "api", f"repos/{login}/{login}/readme", "--jq", ".content"], capture_output=True, text=True, timeout=20).stdout
        readme = base64.b64decode(raw).decode("utf-8", "replace")
    except Exception:
        return []
    clean = lambda t: " ".join(html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("Visit site →", "").split())
    out = []
    for table in re.findall(r"<table.*?</table>", readme, re.S):
        titles = [clean(t) for t in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S)]
        rows = re.findall(r"<tr>(.*?)</tr>", table, re.S)
        imgs = [re.findall(r'<img[^>]*src="([^"]+)"', c) for c in re.findall(r"<td[^>]*>(.*?)</td>", rows[1], re.S)] if len(rows) > 1 else []
        texts = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", rows[2], re.S)] if len(rows) > 2 else []
        links = [re.findall(r'<a href="(https?://[^"]+)"', c) for c in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S)]
        for i, title in enumerate(titles):
            src = (imgs[i] or [""])[0] if i < len(imgs) else ""
            if not title or not src:
                continue
            if not src.startswith("https://"):
                src = f"https://raw.githubusercontent.com/{login}/{login}/main/{src.lstrip('./')}"
            out.append({"kind": "project", "title": title[:60], "text": (texts[i] if i < len(texts) else "")[:200], "when": "",
                        "live": False, "url": (links[i] or [""])[0] if i < len(links) else "", "image": src})
    return out


def work_suggest() -> list[dict]:
    """What to put on your page: your public repositories, and what your agents saw you work on lately."""
    from . import conversations
    out, seen = [], set()
    for w in github_showcase() + github_work():
        if slug(w["title"])[:24] in seen:
            continue
        seen.add(slug(w["title"])[:24])
        out.append(w)
    items = sorted(conversations.all_listed()["conversations"].values(), key=lambda c: -(c.get("updated") or 0))
    for c in items[:30]:
        title = " ".join((c.get("title") or "").split())[:60]
        key = slug(title)[:24]
        if not title or key in seen or title.lower() in ("new conversation", "salut", "hello"):
            continue
        seen.add(key)
        out.append({"kind": "progress", "title": title, "text": f"with {c.get('brain', 'an agent')}", "when": "lately", "live": True})
        if sum(w["kind"] == "progress" for w in out) >= 4:
            break
    return out


def raw() -> dict:
    """Your local copies, for the sealed sync: extras and the ids of your own reactions."""
    return {"profile": _read(PROFILE, {}), "mine": _read(MINE, {"reactions": {}, "reposts": {}})}


def merge(remote: dict) -> None:
    """Another device of yours: its extras fill what is missing here, its reactions join yours."""
    if not isinstance(remote, dict):
        return
    local = _read(PROFILE, {})
    if not local and isinstance(remote.get("profile"), dict):
        profile_set(remote["profile"])
    mine, theirs = _read(MINE, {"reactions": {}, "reposts": {}}), remote.get("mine") or {}
    changed = False
    for key in ("reactions", "reposts"):
        for post_id, event_id in (theirs.get(key) or {}).items():
            if post_id not in mine.setdefault(key, {}):
                mine[key][post_id] = event_id
                changed = True
    if changed:
        _write(MINE, mine)


# -- the client -------------------------------------------------------------------------------

class Network:
    """Runs on its own loop, like channels.py. Every public method is blocking."""

    def __init__(self, keys, pseudo: str = "", on_event: Callable[[dict], None] = lambda e: None, expire: int = 0):
        self.keys, self.pseudo, self.on_event = keys, pseudo, on_event
        self.me = keys.public_key().to_hex()
        self.expire = expire              # seconds; tests only: events vanish from relays (NIP-40)
        self.client = None
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self._ready = asyncio.run_coroutine_threadsafe(self._start(), self.loop)
        self._profiles: dict[str, dict] = {}      # hex -> {name, pseudo, picture, ...} seen lately

    def _do(self, coro, timeout=40):
        self.ready()          # the first call right after start must not ask relays that are not connected yet
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _start(self):
        n = _n()
        self.client = n.ClientBuilder().build()
        for r in RELAYS:
            await _aw(self.client.add_relay(n.RelayUrl.parse(r)))
        await _aw(self.client.connect(and_wait=timedelta(seconds=6)))

    def ready(self, timeout=30) -> bool:
        try:
            self._ready.result(timeout)
            return True
        except Exception:
            return False

    def close(self):
        try:
            self._do(_aw(self.client.disconnect()), 5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)

    # -- building and sending --------------------------------------------------------------

    def _event(self, kind: int, content: str, tags: list[list[str]]):
        n = _n()
        tags = [list(t) for t in tags] + [["client", TAG]]
        if self.expire:
            tags.append(["expiration", str(int(time.time()) + self.expire)])
        return n.EventBuilder(n.Kind(kind), content).tags([n.Tag.parse(t) for t in tags]).finalize(self.keys)

    async def _send(self, ev) -> dict:
        out = await _aw(self.client.send_event(ev))
        return {"id": ev.id().to_hex(), "at": ev.created_at().as_secs(), "relays": len(out.success)}

    async def _fetch(self, filters: list, seconds: int = 4) -> list:
        n = _n()
        evs = await _aw(self.client.fetch_events(n.ReqTarget.auto(filters), timeout=timedelta(seconds=seconds)))
        return evs.to_vec() if hasattr(evs, "to_vec") else list(evs)

    def _f(self):
        return _n().Filter()

    def _pk(self, hexkey: str):
        return _n().PublicKey.parse(hexkey)

    def _eid(self, hexid: str):
        return _n().EventId.parse(hexid)

    # -- your profile --------------------------------------------------------------------------

    def publish_profile(self) -> dict:
        """Kind 0 (what every Nostr app shows) + your root-harness extras (kind 30078)."""
        p, act = profile_local(), activity()
        shown = {"pseudo": self.pseudo, "name": p["name"] or self.pseudo, "both": f"{p['name']} ({self.pseudo})" if p["name"] else self.pseudo}[p["show"]]
        meta = {"name": directory.slug(self.pseudo), "display_name": shown, "about": p["about"],
                "picture": p["picture"] if p["picture"].startswith("https://") else "", "banner": p["banner"] if p["banner"].startswith("https://") else ""}
        extras = {"v": 1, "id": directory.handle(self.pseudo, self.me), "pseudo": self.pseudo, "name": p["name"], "show": p["show"],
                  "school": p["school"], "role": p["role"], "state": p["state"], "level": act["level"], "days": act["days"],
                  "work": p["work"], "communities": p["communities"], "at": p.get("at", ""),
                  # a picture pasted as data stays small here (relays cap events near 100 KB); uploaded ones are just links
                  "picture": p["picture"][:48000], "banner": p["banner"][:48000]}

        async def go():
            a = await self._send(self._event(K_PROFILE, json.dumps({k: v for k, v in meta.items() if v}), []))
            b = await self._send(self._event(K_APPDATA, json.dumps(extras, ensure_ascii=False), [["d", EXTRAS]]))
            return {"profile": a, "extras": b}
        return self._do(go())

    def profile_update(self, fields: dict) -> dict:
        profile_set(fields)
        sent = self.publish_profile()
        if "pinned" in fields:
            self.badges_pin(profile_local()["pinned"])
        return {"profile": self.profile_view(self.me, local=True), "sent": sent}

    def profile_view(self, hexkey: str | None = None, local: bool = False) -> dict:
        """Someone's profile (or yours) as the interface shows it."""
        hexkey = hexkey or self.me
        if local and hexkey == self.me:
            p, act = profile_local(), activity()
            return self._view_profile(hexkey, {"name": directory.slug(self.pseudo), "display_name": ""}, {**p, "pseudo": self.pseudo, "level": act["level"], "days": act["days"]})
        self._profiles.pop(hexkey, None)             # fresh, and through the same @ check as everywhere
        return self._do(self._profiles_of({hexkey}))[hexkey]

    async def _profile_remote(self, hexkey: str) -> dict:
        pk = self._pk(hexkey)
        evs = await self._fetch([self._f().kinds([_n().Kind(K_PROFILE)]).author(pk).limit(1),
                                 self._f().kind(_n().Kind(K_APPDATA)).author(pk).identifier(EXTRAS).limit(1)])
        meta, extras = {}, {}
        for ev in evs:
            try:
                data = json.loads(ev.content() or "{}")
            except ValueError:
                continue
            if ev.kind().as_u16() == K_PROFILE:
                meta = data
            else:
                extras = data
        return self._view_profile(hexkey, meta, extras)

    def _view_profile(self, hexkey: str, meta: dict, extras: dict) -> dict:
        pseudo = str(extras.get("pseudo") or meta.get("name") or "")[:32]
        v = {"hex": hexkey, "npub": self._pk(hexkey).to_bech32(), "pseudo": pseudo,
             "id": directory.handle(pseudo, hexkey) if pseudo else "",
             "name": str(extras.get("name") or "")[:60], "show": extras.get("show") if extras.get("show") in ("pseudo", "name", "both") else "pseudo",
             "display": str(meta.get("display_name") or meta.get("name") or pseudo)[:80],
             "about": str(extras.get("about") or meta.get("about") or "")[:300],
             "picture": str(extras.get("picture") or meta.get("picture") or "")[:120000],
             "banner": str(extras.get("banner") or meta.get("banner") or "")[:160000],
             "school": str(extras.get("school") or "")[:60], "role": str(extras.get("role") or "")[:80],
             "state": extras.get("state") if extras.get("state") in STATES else "",
             "level": int(extras.get("level") or 0) if str(extras.get("level", "0")).isdigit() else 0,
             "work": [_work_item(w) for w in (extras.get("work") or []) if isinstance(w, dict) and w.get("title")][:12],
             "communities": [slug(c) for c in (extras.get("communities") or []) if slug(c)][:30],
             "at": at_norm(extras.get("at", "")),
             "mine": hexkey == self.me}
        v["level_label"] = level_label(v["level"])
        if hexkey == self.me and not (meta or extras):
            p, act = profile_local(), activity()   # your own page: what this device knows, if the relays said nothing
            return self._view_profile(hexkey, {"name": directory.slug(self.pseudo)}, {**p, "pseudo": self.pseudo, "level": act["level"], "days": act["days"]})
        if meta or extras:
            self._profiles[hexkey] = v                 # an empty answer is not kept: next time we ask again
        return v

    async def _profiles_of(self, hexkeys: set[str]) -> dict[str, dict]:
        """Many profiles in two fetches, for the feed."""
        n = _n()
        missing = [h for h in hexkeys if h not in self._profiles]
        if missing:
            pks = [self._pk(h) for h in missing]
            evs = await self._fetch([self._f().kinds([n.Kind(K_PROFILE)]).authors(pks),
                                     self._f().kind(n.Kind(K_APPDATA)).authors(pks).identifier(EXTRAS)])
            metas, extras = {}, {}
            for ev in sorted(evs, key=lambda e: e.created_at().as_secs()):
                try:
                    data = json.loads(ev.content() or "{}")
                except ValueError:
                    continue
                (metas if ev.kind().as_u16() == K_PROFILE else extras)[ev.author().to_hex()] = data
            for h in missing:
                self._view_profile(h, metas.get(h, {}), extras.get(h, {}))
            # an @ shows only if that person really owns it (the first claim): nobody can wear someone else's
            ats = {h: self._profiles[h]["at"] for h in missing if h in self._profiles and self._profiles[h].get("at")}
            if ats:
                owners = await self._at_owners(set(ats.values()))
                for h, a in ats.items():
                    if owners.get(a) != h:
                        self._profiles[h]["at"] = ""
        return {h: self._profiles.get(h) or self._view_profile(h, {}, {}) for h in hexkeys}

    # -- posting ---------------------------------------------------------------------------------

    def post(self, text: str, media: list[dict] | None = None, community: str = "", agent: str = "",
             reply_to: dict | None = None) -> dict:
        """A post (kind 1). reply_to = {"id", "author"} for a reply. media = [{"url", "mime", "dim"}]."""
        text = str(text or "").strip()[:4000]
        media = [m for m in (media or []) if isinstance(m, dict) and str(m.get("url", "")).startswith("https://")][:4]
        if not text and not media:
            return {"error": "Nothing to post."}
        tags = [["t", TAG]]
        if community and slug(community):
            tags.append(["t", slug(community)])
        if agent:
            tags.append(["rh-agent", str(agent)[:40]])
        for m in media:
            tags.append(["imeta", f"url {m['url']}", f"m {m.get('mime', 'image/jpeg')}"] + ([f"dim {m['dim']}"] if m.get("dim") else []))
        if reply_to and reply_to.get("id"):
            tags += [["e", reply_to["id"], RELAYS[0], "root"], ["p", reply_to.get("author", self.me)]]
        content = text + ("\n" + "\n".join(m["url"] for m in media) if media else "")
        sent = self._do(self._send(self._event(K_POST, content, tags)))
        self.on_event({"type": "network_posted", "id": sent["id"]})
        return sent

    def repost(self, post: dict) -> dict:
        """Kind 6: the original event (its JSON) travels inside."""
        if not post.get("raw"):
            return {"error": "Nothing to repost."}
        tags = [["e", post["id"], RELAYS[0]], ["p", post["author"]["hex"] if isinstance(post.get("author"), dict) else post.get("author", "")]]
        sent = self._do(self._send(self._event(K_REPOST, post["raw"], tags)))
        mine = _read(MINE, {"reactions": {}, "reposts": {}})
        mine["reposts"][post["id"]] = sent["id"]
        _write(MINE, mine)
        return sent

    def react(self, post_id: str, author: str, on: bool = True) -> dict:
        """Kind 7 "+" ; taking it back publishes a deletion (NIP-09) of your reaction."""
        mine = _read(MINE, {"reactions": {}, "reposts": {}})
        if on:
            if post_id in mine["reactions"]:
                return {"id": mine["reactions"][post_id], "already": True}
            sent = self._do(self._send(self._event(K_REACTION, "+", [["e", post_id, RELAYS[0]], ["p", author], ["k", str(K_POST)]])))
            mine["reactions"][post_id] = sent["id"]
        else:
            rid = mine["reactions"].pop(post_id, None)
            if not rid:
                return {"removed": False}
            sent = self._do(self._send(self._event(K_DELETE, "", [["e", rid], ["k", str(K_REACTION)]])))
            sent["removed"] = True
        _write(MINE, mine)
        return sent

    def unrepost(self, post_id: str) -> dict:
        mine = _read(MINE, {"reactions": {}, "reposts": {}})
        rid = mine["reposts"].pop(post_id, None)
        if not rid:
            return {"removed": False}
        sent = self._do(self._send(self._event(K_DELETE, "", [["e", rid], ["k", str(K_REPOST)]])))
        _write(MINE, mine)
        return {**sent, "removed": True}

    def delete_post(self, post_id: str) -> dict:
        return self._do(self._send(self._event(K_DELETE, "", [["e", post_id], ["k", str(K_POST)]])))

    # -- reading ----------------------------------------------------------------------------------

    def feed(self, scope: str = "for-you", community: str = "", friends: list[str] | None = None,
             days: int = 7, limit: int = 60) -> list[dict]:
        """scope: for-you (everyone on root-harness + your friends), friends, community, me."""
        return self._do(self._feed(scope, community, friends or [], days, limit), 60)

    async def _feed(self, scope, community, friends, days, limit) -> list[dict]:
        n = _n()
        since = n.Timestamp.from_secs(int(time.time()) - days * 86400)
        kinds = [n.Kind(K_POST), n.Kind(K_REPOST)]
        filters = []
        if scope == "for-you":
            filters.append(self._f().kinds(kinds).hashtag(TAG).since(since).limit(limit))
            if friends:
                filters.append(self._f().kinds(kinds).authors([self._pk(h) for h in friends[:200]]).since(since).limit(limit))
        elif scope == "friends":
            if not friends:
                return []
            filters.append(self._f().kinds(kinds).authors([self._pk(h) for h in friends[:200] + [self.me]]).since(since).limit(limit))
        elif scope == "community":
            if not slug(community):
                return []
            # a community is a hashtag; keep what was posted from root-harness (#root-harness too), not all of Nostr
            filters.append(self._f().kinds(kinds).hashtag(slug(community)).since(since).limit(limit * 3))
        elif scope == "me":
            filters.append(self._f().kinds(kinds).author(self._pk(self.me)).limit(limit))
        evs = await self._fetch(filters)
        if scope == "community":
            evs = [e for e in evs if any(t[:2] == ["t", TAG] for t in _tags(e))]
        return await self._hydrate(evs, limit)

    async def _hydrate(self, evs, limit: int) -> list[dict]:
        """Events -> posts with their authors, counts and what you did on them."""
        n = _n()
        posts, by_id = [], {}
        for ev in evs:
            p = self._post_of(ev)
            if p and p["id"] not in by_id:
                by_id[p["id"]] = p
                posts.append(p)
        posts.sort(key=lambda p: -p["at"])
        posts = posts[:limit]
        ids = [p["id"] for p in posts]

        async def counts_of():
            return await self._fetch([self._f().kinds([n.Kind(K_POST), n.Kind(K_REPOST), n.Kind(K_REACTION)]).events([self._eid(i) for i in ids]).limit(2000)], 6) if ids else []
        # the counts and the authors at the same time
        counts, authors = await asyncio.gather(counts_of(), self._profiles_of(
            {p["author"]["hex"] for p in posts} | {p["reposted_by"]["hex"] for p in posts if p.get("reposted_by")}))
        if ids:
            for ev in counts:
                tags = _tags(ev)
                kind = ev.kind().as_u16()
                for t in tags:
                    if len(t) > 1 and t[0] == "e" and t[1] in by_id:
                        p = by_id[t[1]]
                        key = "replies" if kind == K_POST else "reposts" if kind == K_REPOST else "reactions"
                        p["counts"][key] += 1
                        if ev.author().to_hex() == self.me:
                            p["mine"]["repost" if kind == K_REPOST else "reaction" if kind == K_REACTION else "reply"] = True
                        break
        for p in posts:
            p["author"] = authors.get(p["author"]["hex"], p["author"])
            if p.get("reposted_by"):
                p["reposted_by"] = authors.get(p["reposted_by"]["hex"], p["reposted_by"])
        return posts

    def _post_of(self, ev) -> dict | None:
        kind = ev.kind().as_u16()
        reposted_by = None
        if kind == K_REPOST:
            try:
                inner = _n().Event.from_json(ev.content())
                if not inner.verify():
                    return None
            except Exception:
                return None
            reposted_by = {"hex": ev.author().to_hex(), "at": ev.created_at().as_secs()}
            ev = inner
        elif kind != K_POST:
            return None
        tags = _tags(ev)
        media = []
        for t in tags:
            if t and t[0] == "imeta":
                parts = dict(x.split(" ", 1) for x in t[1:] if " " in x)
                if str(parts.get("url", "")).startswith("https://"):
                    media.append({"url": parts["url"], "mime": parts.get("m", ""), "dim": parts.get("dim", "")})
        text = ev.content()
        for m in media:                                   # the link is in the text for other apps: not shown twice here
            text = text.replace(m["url"], "").rstrip()
        root = next((t[1] for t in tags if len(t) > 1 and t[0] == "e"), "")
        communities = [t[1] for t in tags if len(t) > 1 and t[0] == "t" and t[1] != TAG]
        return {"id": ev.id().to_hex(), "at": ev.created_at().as_secs(), "author": {"hex": ev.author().to_hex()},
                "text": text[:4000], "media": media, "community": communities[0] if communities else "",
                "agent": _first(tags, "rh-agent"), "reply_to": root, "from_root_harness": any(t[:2] == ["t", TAG] for t in tags),
                "counts": {"replies": 0, "reposts": 0, "reactions": 0}, "mine": {"reaction": False, "repost": False, "reply": False},
                "reposted_by": reposted_by, "raw": ev.as_json()}

    def thread(self, post_id: str) -> dict:
        return self._do(self._thread(post_id), 40)

    async def _thread(self, post_id: str) -> dict:
        n = _n()
        evs = await self._fetch([self._f().ids([self._eid(post_id)]), self._f().kind(n.Kind(K_POST)).events([self._eid(post_id)]).limit(200)])
        posts = await self._hydrate(evs, 201)
        root = next((p for p in posts if p["id"] == post_id), None)
        replies = sorted((p for p in posts if p["id"] != post_id), key=lambda p: p["at"])
        return {"post": root, "replies": replies}

    def wall(self, hexkey: str | None = None, limit: int = 60) -> dict:
        """Someone's page: profile, badges, posts, replies, reposts and media."""
        return self._do(self._wall(hexkey or self.me, limit), 60)

    async def _wall(self, hexkey: str, limit: int) -> dict:
        n = _n()
        pk = self._pk(hexkey)
        async def posts_of():
            return await self._hydrate(await self._fetch([self._f().kinds([n.Kind(K_POST), n.Kind(K_REPOST)]).author(pk).limit(limit)]), limit)

        async def mine_of():
            return await self._follows_of(self.me) if hexkey != self.me else None
        # everything at once: the page waits for the slowest answer, not for the sum of them
        posts, profiles, badges, following, followers, mine = await asyncio.gather(
            posts_of(), self._profiles_of({hexkey}), self._badges_of(hexkey), self._follows_of(hexkey), self._followers_of(hexkey), mine_of())
        profile = profiles[hexkey]
        mine = following if mine is None else mine
        return {"profile": profile, "badges": badges,
                "following": following, "followers": followers,
                "i_follow": hexkey in mine, "follows_me": self.me in following,
                "posts": [p for p in posts if not p["reply_to"] and not p.get("reposted_by")],
                "replies": [p for p in posts if p["reply_to"] and not p.get("reposted_by")],
                "reposts": [p for p in posts if p.get("reposted_by")],
                "media": [p for p in posts if p["media"] and not p.get("reposted_by")]}

    # -- following (kind 3, the list every Nostr app shares) -----------------------------------------

    async def _contact_list(self, hexkey: str):
        evs = await self._fetch([self._f().kind(_n().Kind(K_FOLLOWS)).author(self._pk(hexkey)).limit(1)])
        return max(evs, key=lambda e: e.created_at().as_secs()) if evs else None

    async def _follows_of(self, hexkey: str) -> list[str]:
        ev = await self._contact_list(hexkey)
        if not ev:
            return []
        seen, out = set(), []
        for t in _tags(ev):
            if len(t) > 1 and t[0] == "p" and re.fullmatch(r"[0-9a-f]{64}", t[1]) and t[1] not in seen and t[1] != hexkey:
                seen.add(t[1])
                out.append(t[1])
        return out

    async def _followers_of(self, hexkey: str) -> list[str]:
        """Whose latest list names this person (relays keep only the latest list of each)."""
        evs = await self._fetch([self._f().kind(_n().Kind(K_FOLLOWS)).pubkey(self._pk(hexkey)).limit(500)])
        latest = {}
        for ev in evs:
            a = ev.author().to_hex()
            if a != hexkey and (a not in latest or ev.created_at().as_secs() > latest[a].created_at().as_secs()):
                latest[a] = ev
        return [a for a, ev in latest.items() if any(t[:2] == ["p", hexkey] for t in _tags(ev))]

    def following(self, hexkey: str | None = None) -> list[str]:
        return self._do(self._follows_of(hexkey or self.me))

    def follow(self, hexkey: str, on: bool = True) -> dict:
        """Add or remove one person from your list, keeping everything else in it (other apps' entries too)."""
        if not re.fullmatch(r"[0-9a-f]{64}", hexkey or "") or hexkey == self.me:
            return {"error": "Nobody to follow."}

        async def go():
            ev = await self._contact_list(self.me)
            tags = [t for t in (_tags(ev) if ev else []) if t]
            content = ev.content() if ev else ""
            has = any(t[:2] == ["p", hexkey] for t in tags)
            if on and not has:
                tags.append(["p", hexkey])
            if not on:
                tags = [t for t in tags if t[:2] != ["p", hexkey]]
            n = _n()
            out = n.EventBuilder(n.Kind(K_FOLLOWS), content).tags([n.Tag.parse(t) for t in tags]).finalize(self.keys)
            sent = await self._send(out)       # never with an expiration: this list replaces the one other apps see
            return {**sent, "following": on, "count": sum(1 for t in tags if t[0] == "p")}
        return self._do(go())

    def people(self, hexkeys: list[str]) -> list[dict]:
        """Profiles for a list (followers, following), in the given order."""
        hexkeys = [h for h in hexkeys if re.fullmatch(r"[0-9a-f]{64}", h or "")][:300]
        got = self._do(self._profiles_of(set(hexkeys)), 60) if hexkeys else {}
        return [got[h] for h in hexkeys if h in got]

    # -- notifications: what people did with you -----------------------------------------------------

    def notifications(self, days: int = 30, limit: int = 120) -> dict:
        return self._do(self._notifications(days, limit), 60)

    async def _notifications(self, days: int, limit: int) -> dict:
        n = _n()
        since = n.Timestamp.from_secs(int(time.time()) - days * 86400)
        me = self._pk(self.me)
        evs = await self._fetch([self._f().kinds([n.Kind(K_POST), n.Kind(K_REPOST), n.Kind(K_REACTION), n.Kind(K_AWARD)]).pubkey(me).since(since).limit(limit * 2),
                                 self._f().kind(n.Kind(K_FOLLOWS)).pubkey(me).limit(500)])
        state = _read(NOTIFS, {"seen_at": 0, "followers": {}, "pushed_at": 0})
        items, targets, now = [], set(), int(time.time())
        for ev in evs:
            who, kind, tags = ev.author().to_hex(), ev.kind().as_u16(), _tags(ev)
            if who == self.me:
                continue
            at = ev.created_at().as_secs()
            if kind == K_FOLLOWS:
                if not any(t[:2] == ["p", self.me] for t in tags):
                    continue
                at = state["followers"].setdefault(who, now if state["followers"] else at)   # a follow counts once, when first seen
                items.append({"id": "f" + who, "type": "follow", "at": at, "who": who})
                continue
            target = next((t[1] for t in tags if len(t) > 1 and t[0] == "e"), "")
            if kind == K_REACTION:
                items.append({"id": ev.id().to_hex(), "type": "like", "at": at, "who": who, "post": target})
            elif kind == K_REPOST:
                items.append({"id": ev.id().to_hex(), "type": "repost", "at": at, "who": who, "post": target})
            elif kind == K_POST:
                items.append({"id": ev.id().to_hex(), "type": "reply" if target else "mention", "at": at, "who": who, "post": target, "text": ev.content()[:280]})
            elif kind == K_AWARD:
                a = _first(tags, "a")
                items.append({"id": ev.id().to_hex(), "type": "badge", "at": at, "who": who, "badge": a})
            if target:
                targets.add(target)
        # people who unfollowed are forgotten, so a new follow later shows again
        current = {i["who"] for i in items if i["type"] == "follow"}
        state["followers"] = {h: t for h, t in state["followers"].items() if h in current}
        _write(NOTIFS, state)
        texts = {}
        if targets:
            for ev in await self._fetch([self._f().ids([self._eid(t) for t in list(targets)[:300]])]):
                texts[ev.id().to_hex()] = ev.content()[:140]
        badge_names = {}
        for b in [i for i in items if i["type"] == "badge"]:
            parts = b["badge"].split(":", 2)
            if len(parts) == 3:
                badge_names[b["badge"]] = parts[2].replace("-", " ")
        people = await self._profiles_of({i["who"] for i in items})
        items.sort(key=lambda i: -i["at"])
        items = items[:limit]
        for i in items:
            i["person"] = people.get(i["who"]) or {"hex": i["who"]}
            if i.get("post"):
                i["post_text"] = texts.get(i["post"], "")
            if i["type"] == "badge":
                i["badge_name"] = badge_names.get(i["badge"], "a badge")
            i["new"] = i["at"] > state["seen_at"]
        return {"items": items, "unread": sum(1 for i in items if i["new"]), "seen_at": state["seen_at"]}

    def notifications_seen(self) -> int:
        state = _read(NOTIFS, {"seen_at": 0, "followers": {}, "pushed_at": 0})
        state["seen_at"] = int(time.time())
        _write(NOTIFS, state)
        return state["seen_at"]

    def notifications_new(self) -> dict:
        """For the dot on the tab, and what to tell the phones once (computer only)."""
        got = self.notifications(days=7, limit=60)
        state = _read(NOTIFS, {"seen_at": 0, "followers": {}, "pushed_at": 0})
        fresh = [i for i in got["items"] if i["at"] > max(state.get("pushed_at", 0), state["seen_at"])]
        if fresh:
            state["pushed_at"] = max(i["at"] for i in fresh)
            _write(NOTIFS, state)
        return {"unread": got["unread"], "fresh": fresh[:5]}

    # -- your @, like on X: the first one to claim a name has it -------------------------------------

    async def _at_owners(self, names: set[str]) -> dict[str, str]:
        n = _n()
        names = {a for a in names if a}
        if not names:
            return {}
        evs = await self._fetch([self._f().kind(n.Kind(K_APPDATA)).identifiers([AT + a for a in names]).limit(500)])
        best: dict[str, tuple] = {}
        for ev in evs:
            d = _first(_tags(ev), "d")
            a = d[len(AT):] if d.startswith(AT) else ""
            try:
                ok = a in names and json.loads(ev.content() or "{}").get("at") == a
            except ValueError:
                ok = False
            if ok:
                key = (ev.created_at().as_secs(), ev.author().to_hex())
                if a not in best or key < best[a]:
                    best[a] = key
        return {a: k[1] for a, k in best.items()}

    def at_owner(self, name: str) -> str | None:
        a = at_norm(name)
        return self._do(self._at_owners({a})).get(a) if a else None

    def claim_at(self, name: str) -> dict:
        """Take @name if nobody has it; your old @ is let go."""
        a = at_norm(name)
        if not a:
            return {"error": "3 to 20 letters, digits or _."}
        owner = self.at_owner(a)
        if owner and owner != self.me:
            return {"error": f"@{a} is taken."}
        old = profile_local().get("at", "")

        async def go():
            n = _n()
            ev = n.EventBuilder(n.Kind(K_APPDATA), json.dumps({"at": a})).tags([n.Tag.parse(["d", AT + a])]).finalize(self.keys)
            sent = await self._send(ev)
            if old and old != a:
                await self._send(n.EventBuilder(n.Kind(K_APPDATA), "").tags([n.Tag.parse(["d", AT + old])]).finalize(self.keys))
            return sent
        sent = self._do(go())
        p = profile_local()
        p["at"] = a
        _write(PROFILE, p)
        self._profiles.pop(self.me, None)
        self.publish_profile()
        return {**sent, "at": a}

    def lookup(self, text: str) -> dict | None:
        """@name, vincent#k7f2qa9m or an npub -> that person's profile."""
        if (text or "").strip().startswith("@") or (at_norm(text) and "#" not in text and not text.strip().startswith("npub")):
            owner = self.at_owner(text)
            if owner:
                return self.profile_view(owner)
            if text.strip().startswith("@"):
                return None
        card = asyncio.run(directory.lookup(text)) if directory.parse(text) else None
        if not card:
            try:
                return self.profile_view(self._pk(text.strip()).to_hex())
            except Exception:
                return None
        return self.profile_view(card["hex"])

    # -- pictures and videos: a public media host, signed with your key (NIP-96 + NIP-98) ----------

    def upload(self, path: str) -> dict:
        p = Path(path)
        data = p.read_bytes()
        if len(data) > MEDIA_MAX:
            return {"error": "Too big: 20 MB at most."}
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if not mime.startswith(("image/", "video/", "audio/")):
            return {"error": "Only pictures, videos and audio."}
        return self.upload_bytes(data, mime, p.name)

    def upload_bytes(self, data: bytes, mime: str, name: str = "file") -> dict:
        if not data or len(data) > MEDIA_MAX:
            return {"error": "Empty file, or too big: 20 MB at most."}
        if not str(mime).startswith(("image/", "video/", "audio/")):
            return {"error": "Only pictures, videos and audio."}
        n = _n()
        auth = n.EventBuilder(n.Kind(K_AUTH), "").tags([n.Tag.parse(["u", MEDIA_HOST]), n.Tag.parse(["method", "POST"]),
                                                        n.Tag.parse(["payload", hashlib.sha256(data).hexdigest()])]).finalize(self.keys)
        boundary = "----rh" + uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\nContent-Type: {mime}\r\n\r\n").encode() + data + \
               (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"no_transform\"\r\n\r\nfalse\r\n--{boundary}--\r\n").encode()
        req = urllib.request.Request(MEDIA_HOST, data=body, method="POST", headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": "Nostr " + base64.b64encode(auth.as_json().encode()).decode()})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out = json.load(r)
        except Exception as e:
            return {"error": f"Upload failed: {type(e).__name__}: {str(e)[:120]}"}
        tags = out.get("nip94_event", {}).get("tags", [])
        url = _first(tags, "url")
        if not url.startswith("https://"):
            return {"error": "Upload failed: " + str(out.get("message", ""))[:120]}
        return {"url": url, "mime": _first(tags, "m", mime), "dim": _first(tags, "dim")}

    # -- badges (NIP-58) ------------------------------------------------------------------------------

    def badge_define(self, ident: str, name: str, description: str, image: str = "") -> dict:
        """A badge you create (for an event, a team, a promise kept). Coordinate: 30009:<you>:<ident>."""
        ident = slug(ident)
        if not ident or not name.strip():
            return {"error": "A badge needs an id and a name."}
        tags = [["d", ident], ["name", name.strip()[:60]], ["description", description.strip()[:300]]]
        if image:
            tags.append(["image", image[:120000], "64x64"])
        sent = self._do(self._send(self._event(K_BADGE, "", tags)))
        return {**sent, "a": f"{K_BADGE}:{self.me}:{ident}"}

    def badge_award(self, a: str, recipients: list[str]) -> dict:
        """Give a badge you defined (a = its coordinate) to people (hex keys)."""
        if not a.startswith(f"{K_BADGE}:{self.me}:"):
            return {"error": "You can only award badges you created."}
        recipients = [r for r in recipients if re.fullmatch(r"[0-9a-f]{64}", r or "")]
        if not recipients:
            return {"error": "Nobody to award."}
        tags = [["a", a]] + [["p", r, RELAYS[0]] for r in recipients[:200]]
        return self._do(self._send(self._event(K_AWARD, "", tags)))

    def badges_mine(self) -> list[dict]:
        return self._do(self._badges_of(self.me), 40)

    async def _badges_of(self, hexkey: str) -> list[dict]:
        """Awards to this person, with their definitions and whether they are pinned."""
        n = _n()
        pk = self._pk(hexkey)
        evs = await self._fetch([self._f().kind(n.Kind(K_AWARD)).pubkey(pk).limit(200),
                                 self._f().kind(n.Kind(K_PINNED)).author(pk).identifier("profile_badges").limit(1)])
        awards, pinned = {}, []
        for ev in evs:
            tags = _tags(ev)
            if ev.kind().as_u16() == K_AWARD:
                a = _first(tags, "a")
                if a.startswith(f"{K_BADGE}:") and a.split(":")[1] == ev.author().to_hex():     # only the creator can award it
                    awards.setdefault(a, {"a": a, "award": ev.id().to_hex(), "issuer": ev.author().to_hex(), "at": ev.created_at().as_secs()})
            else:
                pinned = [t[1] for t in tags if len(t) > 1 and t[0] == "a"]
        if not awards:
            return []
        by_issuer: dict[str, list[str]] = {}
        for a in awards:
            _, issuer, d = a.split(":", 2)
            by_issuer.setdefault(issuer, []).append(d)
        # the definitions themselves (kind 30009 by its creator, #d): not the events that mention them
        defs = {}
        for ev in await self._fetch([self._f().kind(n.Kind(K_BADGE)).author(self._pk(i)).identifiers(ds) for i, ds in by_issuer.items()]):
            tags = _tags(ev)
            defs[f"{K_BADGE}:{ev.author().to_hex()}:{_first(tags, 'd')}"] = {"name": _first(tags, "name"), "description": _first(tags, "description"),
                                                                              "image": _first(tags, "image")}
        issuers = await self._profiles_of({v["issuer"] for v in awards.values()})
        out = []
        for a, v in awards.items():
            d = defs.get(a)
            if not d:
                continue
            out.append({**v, **d, "pinned": a in pinned, "self": v["issuer"] == hexkey,
                        "issuer_name": issuers.get(v["issuer"], {}).get("id") or issuers.get(v["issuer"], {}).get("display", "")})
        out.sort(key=lambda b: (not b["pinned"], -b["at"]))
        return out

    def badges_pin(self, coords: list[str]) -> dict:
        """What shows on your profile (kind 30008): pairs of a + award id, in order."""
        mine = {b["a"]: b for b in self.badges_mine()}
        tags = [["d", "profile_badges"]]
        kept = []
        for a in coords:
            b = mine.get(a)
            if b:
                tags += [["a", a], ["e", b["award"], RELAYS[0]]]
                kept.append(a)
        profile_set({"pinned": kept})
        return {**self._do(self._send(self._event(K_PINNED, "", tags))), "pinned": kept}

    # the automatic badges: your own root-harness certifies them (shown as self-certified)
    AUTO = {
        "first-post": ("First post", "Posted for the first time."),
        "seven-days": ("7 days in a row", "Worked with the agents seven days in a row."),
        "encyclopedist": ("Encyclopedist", "Fifty words in the encyclopedia."),
        "night-shift": ("Night shift", "A post between two and five in the morning."),
        "shipped": ("Shipped", "A project finished and shown."),
        "hackathon": ("Hackathon", "Took part in a hackathon."),
    }

    def badges_check(self) -> list[str]:
        """Earned automatic badges not yet awarded: define, award to yourself, return the new ones."""
        from . import conversations, glossary
        earned = set()
        wall = self._do(self._feed("me", "", [], 3650, 200), 40)
        posts = [p for p in wall if not p.get("reposted_by")]
        if posts:
            earned.add("first-post")
        if any(2 <= time.localtime(p["at"]).tm_hour < 5 for p in posts):
            earned.add("night-shift")
        if len(glossary.listing()["terms"]) - len(glossary.base()) >= 50:
            earned.add("encyclopedist")
        days = sorted({int(((c.get("updated") or 0) / 1000) // 86400) for c in conversations.all_listed()["conversations"].values()})
        run = best = 0
        for i, d in enumerate(days):
            run = run + 1 if i and d == days[i - 1] + 1 else 1
            best = max(best, run)
        if best >= 7:
            earned.add("seven-days")
        work = profile_local()["work"]
        if any(w.get("kind") == "project" and not w.get("live") for w in work):
            earned.add("shipped")
        if any(w.get("kind") == "hackathon" for w in work):
            earned.add("hackathon")
        have = {b["a"] for b in self.badges_mine()}
        new = []
        for ident in sorted(earned):
            a = f"{K_BADGE}:{self.me}:{ident}"
            if a in have:
                continue
            name, desc = self.AUTO[ident]
            self.badge_define(ident, name, desc)
            self.badge_award(a, [self.me])
            new.append(ident)
        if new:
            self.on_event({"type": "badges_new", "badges": new})
        return new

    # -- communities (NIP-72 definition + the hashtag that carries the posts) ---------------------------

    def community_create(self, name: str, description: str = "") -> dict:
        d = slug(name)
        if not d:
            return {"error": "Give the community a name."}
        tags = [["d", d], ["name", name.strip()[:60]], ["description", description.strip()[:300]],
                ["p", self.me, RELAYS[0], "moderator"], ["t", TAG]]          # #root-harness: found by communities()
        sent = self._do(self._send(self._event(K_COMMUNITY, "", tags)))
        p = profile_local()
        profile_set({"communities": p["communities"] + [d]})
        return {**sent, "slug": d, "a": f"{K_COMMUNITY}:{self.me}:{d}"}

    def communities(self, limit: int = 60) -> list[dict]:
        """Communities people made from root-harness, newest first, with the ones you joined flagged."""
        return self._do(self._communities(limit), 40)

    async def _communities(self, limit: int) -> list[dict]:
        n = _n()
        evs = await self._fetch([self._f().kind(n.Kind(K_COMMUNITY)).hashtag(TAG).limit(limit)])
        mine = set(profile_local()["communities"])
        out, seen = [], set()
        for ev in sorted(evs, key=lambda e: -e.created_at().as_secs()):
            tags = _tags(ev)
            d = _first(tags, "d")
            if not d or d in seen:
                continue
            seen.add(d)
            out.append({"slug": d, "name": _first(tags, "name", d), "description": _first(tags, "description"),
                        "by": ev.author().to_hex(), "joined": d in mine, "a": f"{K_COMMUNITY}:{ev.author().to_hex()}:{d}"})
        return out

    def community_join(self, d: str, on: bool = True) -> list[str]:
        p = profile_local()
        cs = set(p["communities"])
        (cs.add if on else cs.discard)(slug(d))
        return profile_set({"communities": sorted(cs)})["communities"]
