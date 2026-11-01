"""The backend's sharp edges, without relays, keychain or a real gh: a turn that
cannot save, gh that never prints its code, partial relay answers, a locked
account, what a contact can put in a shared conversation, private files.
Run:  .venv/bin/python -m pytest -q tests/test_window_fixes.py"""
import asyncio
import json
import os
import stat
import tempfile
import threading
import time
import types
import unittest
import urllib.request
import webbrowser
from pathlib import Path
from unittest import mock

os.environ.setdefault("ROOT_HARNESS_HOME", tempfile.mkdtemp(prefix="rh-test-"))

from rootharness import window, conversations, account, network, channels   # noqa: E402  (after the home is set)

ME = "a" * 64


def bare_api():
    """An Api without its __init__ (no sync, no relays, no brain)."""
    api = object.__new__(window.Api)
    api._busy, api._pending, api._next = threading.Lock(), {}, 0
    api.conv, api.log, api._window, api.remote, api._web = None, {"events": []}, None, None, None
    api.keys = api.sync = api.channels = api.network = api.pairing = None
    api._emit = lambda e: None
    return api


class FakeKeyring:
    def __init__(self, fail=False):
        self.fail = fail

    def get_password(self, *a):
        if self.fail:
            raise RuntimeError("keychain locked")
        return None

    def delete_password(self, *a):
        pass


# -- 1. a failed save never keeps the next message out ------------------------------------

class Busy(unittest.TestCase):
    def test_lock_released_when_save_fails(self):
        api = bare_api()
        api.conv, seen = "c1", []
        api._emit = seen.append
        api.session = types.SimpleNamespace(model=None, run_turn=lambda prompt, emit: emit({"type": "text", "text": "hi"}))
        with mock.patch.object(conversations, "write_log", side_effect=OSError(28, "No space left on device")), \
                mock.patch.object(window.glossary, "auto", return_value=False):
            api._run("hello")
        self.assertFalse(api._busy.locked())
        self.assertTrue(any(e.get("type") == "error" and "No space" in e.get("text", "") for e in seen))


# -- 2. gh sign-in: a deadline, colours off, one gh at a time, "Later" ----------------------

FAKE_GH = """#!/bin/sh
if [ "$1" = "api" ]; then echo "not logged in" >&2; exit 1; fi
if [ "$1" = "auth" ] && [ "$2" = "login" ]; then
  echo "spawn $$" >> "$FAKELOG"
  case "$MODE" in
    silent) sleep 30 ;;
    code) printf '! First copy your one-time code: ABCD-1234\\n'; sleep 30 ;;
    ansi) printf '! First copy your one-time code: \\033[1mABCD-1234\\033[0m\\n'; sleep 30 ;;
    fail) echo "error connecting to api.github.com"; exit 1 ;;
  esac
fi
"""


class GitHub(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="rh-gh-"))
        gh = self.dir / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.log = self.dir / "log"
        self.env = mock.patch.dict(os.environ, {"PATH": f"{self.dir}:/usr/bin:/bin", "FAKELOG": str(self.log)})
        self.env.start()
        self.wait = mock.patch.object(window, "GH_WAIT", 2)
        self.wait.start()
        self.browser = mock.patch.object(webbrowser, "open", return_value=True)
        self.browser.start()
        self.api = types.SimpleNamespace()

    def tearDown(self):
        window.Api.setup_github_cancel(self.api)
        self.browser.stop()
        self.wait.stop()
        self.env.stop()

    def start(self, mode):
        os.environ["MODE"] = mode
        self.log.write_text("")
        return window.Api.setup_github_start(self.api)

    def spawns(self):
        return len(self.log.read_text().splitlines())

    def test_code(self):
        self.assertEqual(self.start("code")["code"], "ABCD-1234")

    def test_code_in_colour(self):
        self.assertEqual(self.start("ansi")["code"], "ABCD-1234")

    def test_silent_gh_gives_up_and_is_killed(self):
        t = time.time()
        r = self.start("silent")
        self.assertIn("error", r)
        self.assertLess(time.time() - t, 6)
        self.assertIsNone(getattr(self.api, "_gh_proc", None))

    def test_failure_says_what_gh_said(self):
        r = self.start("fail")
        self.assertIn("error connecting to api.github.com", r["error"])

    def test_two_clicks_one_gh(self):
        os.environ["MODE"] = "code"
        self.log.write_text("")
        out = []
        ths = [threading.Thread(target=lambda: out.append(window.Api.setup_github_start(self.api))) for _ in range(2)]
        [t.start() for t in ths]
        [t.join(10) for t in ths]
        self.assertEqual([r.get("code") for r in out], ["ABCD-1234", "ABCD-1234"])
        self.assertEqual(self.spawns(), 1)

    def test_later_kills_gh(self):
        self.start("code")
        p = self.api._gh_proc
        self.assertTrue(window.Api.setup_github_cancel(self.api))
        self.assertIsNotNone(p.poll())
        self.assertEqual(window.Api.setup_github_status(self.api), {"done": False, "failed": False})

    def test_status_survives_setup_git(self):
        self.api._gh_proc = None
        with mock.patch.object(window, "_gh_login", return_value="someone"), \
                mock.patch.object(window.subprocess, "run", side_effect=window.subprocess.TimeoutExpired("gh", 15)):
            self.assertEqual(window.Api.setup_github_status(self.api), {"done": True, "login": "someone"})


# -- 3. followers: once, at the right time, and never lost on one partial answer ----------------

class V:
    def __init__(self, v):
        self.v = v

    def to_hex(self):
        return self.v

    as_u16 = as_secs = to_vec = to_hex


class FollowList:
    def __init__(self, who, at):
        self.who, self.at = who, at

    def author(self):
        return V(self.who)

    def kind(self):
        return V(network.K_FOLLOWS)

    def tags(self):
        return [V(["p", ME])]

    def created_at(self):
        return V(self.at)

    def id(self):
        return V("e" + self.who[:63])

    def content(self):
        return ""


class Followers(unittest.TestCase):
    def setUp(self):
        network.NOTIFS.unlink(missing_ok=True)
        self.net = object.__new__(network.Network)
        self.net.me = ME
        self.long_ago = int(time.time()) - 200 * 86400
        self.evs = [FollowList(c * 64, self.long_ago) for c in "bcd"]

        async def fetch(filters, seconds=4):
            return list(self.evs)

        async def profiles(h):
            return {}
        self.net._fetch, self.net._profiles_of = fetch, profiles     # real filters, no relay

    def look(self):
        return asyncio.run(self.net._notifications(30, 120))

    def test_old_followers_keep_their_date_on_first_look(self):
        r = self.look()
        self.assertEqual(sorted(i["at"] for i in r["items"]), [self.long_ago] * 3)

    def test_partial_answer_does_not_renotify(self):
        self.look()
        self.net.notifications_seen()
        time.sleep(1.1)
        full = list(self.evs)
        self.evs[:] = full[:1]                     # one relay answered, with one list
        r = self.look()
        self.assertEqual({i["who"][0] for i in r["items"]}, {"b", "c", "d"})   # the others are still known
        self.evs[:] = full
        r = self.look()
        self.assertEqual(r["unread"], 0)

    def test_new_follower_later_is_new(self):
        self.look()
        self.net.notifications_seen()
        time.sleep(1.1)
        self.evs.append(FollowList("e" * 64, self.long_ago))
        r = self.look()
        self.assertEqual([i["who"][0] for i in r["items"] if i["new"]], ["e"])


# -- 4. an @ is yours only once a relay keeps it ---------------------------------------------

class ClaimAt(unittest.TestCase):
    def setUp(self):
        import nostr_sdk
        network.PROFILE.unlink(missing_ok=True)
        network.profile_set({"name": ""})
        p = network.profile_local()
        p["at"] = "oldname"
        network._write(network.PROFILE, p)
        self.net = object.__new__(network.Network)
        self.net.keys = nostr_sdk.Keys.generate()
        self.net.me = self.net.keys.public_key().to_hex()
        self.net._profiles = {}
        self.net._do = lambda coro, timeout=40: asyncio.run(coro)
        self.net.at_owner = lambda a: None
        self.net.publish_profile = lambda: {}
        self.sent = []

    def sender(self, relays):
        async def send(ev):
            self.sent.append(ev)
            return {"id": "x", "at": 0, "relays": relays}
        self.net._send = send

    def test_no_relay_connected(self):
        self.net.connected = lambda: 0
        self.sender(3)
        self.assertIn("error", self.net.claim_at("newname"))
        self.assertEqual(network.profile_local()["at"], "oldname")
        self.assertEqual(self.sent, [])

    def test_no_relay_kept_it(self):
        self.net.connected = lambda: 3
        self.sender(0)
        self.assertIn("error", self.net.claim_at("newname"))
        self.assertEqual(network.profile_local()["at"], "oldname")
        self.assertEqual(len(self.sent), 1)         # the old @ was not let go

    def test_kept(self):
        self.net.connected = lambda: 3
        self.sender(2)
        r = self.net.claim_at("newname")
        self.assertEqual(r["at"], "newname")
        self.assertEqual(network.profile_local()["at"], "newname")
        self.assertEqual(len(self.sent), 2)


# -- 5, 10. the account: reset forgets the old page, a keychain error is said ---------------------

class Account(unittest.TestCase):
    def test_reset_clears_the_network_folder(self):
        network.profile_set({"about": "old bio"})
        self.assertTrue((account.HOME / "network" / "profile.json").exists())
        with mock.patch.object(account, "_keyring", return_value=FakeKeyring()):
            account.reset()
        self.assertFalse((account.HOME / "network").exists())
        self.assertEqual(network.profile_local()["about"], "")

    def test_keychain_error_on_create(self):
        with mock.patch.object(account, "_keyring", return_value=FakeKeyring(fail=True)), \
                mock.patch.object(account, "_save") as save:
            keys, why = account.create("someone", "a long password", "a long password")
        self.assertIsNone(keys)
        self.assertIn("keychain", why)
        save.assert_not_called()


# -- 6, 11, 12. locking: pending cards refused, pairing closed, the network answers quietly ----------

class Lock(unittest.TestCase):
    def test_lock_refuses_waiting_permission_and_question(self):
        api = bare_api()
        got = {}
        t1 = threading.Thread(target=lambda: got.update(allow=api._ask("Run a command", {})))
        t2 = threading.Thread(target=lambda: got.update(answers=api._question([{"question": "Which?"}])))
        t1.start(); t2.start()
        for _ in range(100):
            if len(api._pending) == 2:
                break
            time.sleep(0.01)
        api.account_lock()
        t1.join(2); t2.join(2)
        self.assertFalse(t1.is_alive() or t2.is_alive())
        self.assertEqual(got, {"allow": False, "answers": None})

    def test_lock_closes_pairing(self):
        api = bare_api()
        api.pairing = mock.Mock()
        p = api.pairing
        api.account_lock()
        p.close.assert_called_once()
        self.assertIsNone(api.pairing)

    def test_net_calls_when_locked(self):
        api = bare_api()
        for name in [n for n in dir(window.Api) if n.startswith("net_") and n not in ("net_work_suggest", "net_activity")]:
            fn = getattr(api, name)
            n_args = fn.__code__.co_argcount - 1 - len(fn.__defaults__ or ())
            r = fn(*([""] * n_args))
            self.assertNotIsInstance(r, Exception, name)
            if isinstance(r, dict) and "error" in r:
                self.assertIn("Locked", r["error"])
        self.assertEqual(api.net_notifications(), {"items": [], "unread": 0, "seen_at": 0})
        self.assertEqual(api.net_people([]), [])


# -- 7. a page that cannot be reached, a message that cannot be handled ------------------------

class Emit(unittest.TestCase):
    def test_evaluate_js_error_is_swallowed(self):
        api = bare_api()
        api._emit = window.Api._emit.__get__(api)
        api.brain = {"name": "x"}
        api._window = mock.Mock()
        api._window.evaluate_js.side_effect = RuntimeError("JavascriptException")
        api._emit({"type": "text", "text": "hi"})
        self.assertEqual(api.log["events"][-1]["text"], "hi")


class Event:
    def __init__(self, wid):
        self.wid = wid

    def id(self):
        return V(self.wid)

    def kind(self):
        return V(1059)


class Listen(unittest.TestCase):
    def setUp(self):
        channels.STATE.unlink(missing_ok=True)
        self.ch = object.__new__(channels.Channels)
        self.ch.lock = threading.Lock()

    def test_listening_survives_and_retries(self):
        handled = []

        async def handle(ev, wid):
            if wid == "bad":
                raise RuntimeError("the page went away")
            handled.append(wid)
        self.ch._handle = handle
        notes = [types.SimpleNamespace(is_new_event=lambda: True, event=Event(w)) for w in ("bad", "good")] + [None]

        class Stream:
            async def next(self_):
                return notes.pop(0)

        async def stream():
            return Stream()
        self.ch.client = types.SimpleNamespace(notifications=stream)
        asyncio.run(self.ch._listen())
        self.assertEqual(handled, ["good"])
        seen = channels._load()["seen"]
        self.assertIn("good", seen)
        self.assertNotIn("bad", seen)          # fetched again at next launch


# -- XSS: what a contact puts in a shared conversation -------------------------------------------

class Tag:
    def __init__(self, kind, content):
        self._k, self._c = kind, content

    def kind(self):
        return self._k

    def content(self):
        return self._c


class Share(unittest.TestCase):
    TRAP = {"title": {"toString": "<img src=x onerror=alert(1)>"}, "agent": 42, "html": "<script>",
            "events": {"length": "<svg onload=alert(1)>", "0": {"type": "user", "text": "x"}}}

    def test_clean_share(self):
        c = channels.clean_share(json.dumps(self.TRAP))
        self.assertEqual(c, {"rh": "share", "title": "", "agent": "", "events": []})
        c = channels.clean_share({"title": "t" * 500, "events": [{"type": "user", "text": "hi", "x": 1}, {"type": "html", "text": "no"},
                                                                 {"type": "text", "text": ["no"]}, "no", {"type": "text", "text": "y" * 9000}]})
        self.assertEqual(len(c["title"]), 120)
        self.assertEqual(c["events"], [{"type": "user", "text": "hi"}, {"type": "text", "text": "y" * 6000}])
        for bad in ("not json", "[1, 2]", "3", None, []):
            self.assertIsNone(channels.clean_share(bad))

    def test_received_share_is_stored_clean(self):
        channels.STATE.unlink(missing_ok=True)
        friend = "b" * 64
        ch = object.__new__(channels.Channels)
        ch.lock, ch.me, ch.on_remote, emitted = threading.Lock(), ME, None, []
        ch.on_event = emitted.append
        ch._name = lambda h, s=None: "friend"
        rumor = types.SimpleNamespace(kind=lambda: V(14), content=lambda: json.dumps(self.TRAP), created_at=lambda: V(100),
                                      tags=lambda: [Tag("rh-share", "1"), Tag("rh-id", "r1"), Tag("p", "<b>not a key</b>"),
                                                    Tag("subject", "s" * 500)])
        gift = types.SimpleNamespace(rumor=lambda: rumor, sender=lambda: V(friend))

        async def unwrap(keys, ev):
            return gift
        with mock.patch.object(channels, "_n", return_value=types.SimpleNamespace(UnwrappedGift=types.SimpleNamespace(from_gift_wrap=unwrap))):
            ch.keys = None
            asyncio.run(ch._receive(Event("w1")))
        msg = emitted[-1]["message"]
        self.assertEqual(msg["share"], {"rh": "share", "title": "", "agent": "", "events": []})
        self.assertEqual(msg["text"], "shared: ")
        cid = emitted[-1]["channel"]
        self.assertEqual(channels._load()["channels"][cid]["members"], [friend])   # the junk "p" tag is not a member
        self.assertEqual(len(channels._load()["channels"][cid]["name"]), 60)


# -- someone else's profile: pictures are web links or pasted images, nothing else ------------------

class RemoteProfile(unittest.TestCase):
    def setUp(self):
        self.net = object.__new__(network.Network)
        self.net.me, self.net._profiles = ME, {}

    def view(self, extras):
        return self.net._view_profile("c" * 64, {"name": "x"}, extras)

    def test_picture_urls(self):
        for bad in ("javascript:alert(1)", "http://plain.example/a.png", "x\" onerror=\"alert(1)", 42,
                    "data:text/html;base64,PHNjcmlwdD4=", "data:image/svg+xml;base64,PHN2Zz4="):
            v = self.view({"picture": bad, "banner": bad})
            self.assertEqual((v["picture"], v["banner"]), ("", ""), bad)
        v = self.view({"picture": "https://example.com/a.png", "banner": "data:image/png;base64,iVBORw0KGgo="})
        self.assertEqual((v["picture"], v["banner"]), ("https://example.com/a.png", "data:image/png;base64,iVBORw0KGgo="))

    def test_odd_types_do_not_crash(self):
        v = self.view({"communities": "abc", "work": 3, "at": 7})
        self.assertEqual((v["communities"], v["work"], v["at"]), ([], [], ""))


# -- 8, 9. one Network for two calls; the conversation list under several writers ----------------

class Concurrency(unittest.TestCase):
    def test_one_network(self):
        api = bare_api()
        api.keys = object()
        made = []

        def slow(*a, **k):
            time.sleep(0.05)
            made.append(1)
            return object()
        with mock.patch.object(network, "Network", side_effect=slow), \
                mock.patch.object(account, "state", return_value={"pseudo": "x"}):
            ths = [threading.Thread(target=api._net) for _ in range(5)]
            [t.start() for t in ths]
            [t.join(5) for t in ths]
        self.assertEqual(len(made), 1)

    def test_index_writers_lose_nothing(self):
        before = len(conversations.all_listed()["conversations"])
        ths = [threading.Thread(target=conversations.create, args=("ollama", f"t{i}")) for i in range(30)]
        [t.start() for t in ths]
        [t.join(10) for t in ths]
        self.assertEqual(len(conversations.all_listed()["conversations"]), before + 30)

    def test_write_log_is_whole(self):
        conversations.write_log("whole", {"events": [{"type": "text", "text": "x" * 1000}]})
        self.assertEqual(conversations.read_log("whole")["events"][0]["text"], "x" * 1000)
        self.assertEqual(list(conversations.FOLDER.glob("*.tmp")), [])


# -- 13. the phone app is never served stale -----------------------------------------------------

class PhoneApp(unittest.TestCase):
    def test_no_cache_header(self):
        from http import server
        dist = Path(window.__file__).parent.parent / "mobile" / "dist" / "index.html"
        if not dist.exists():
            self.skipTest("the phone app is not built")
        got = {}

        class Capture:
            def __init__(self, addr, handler):
                got["handler"] = handler

            def serve_forever(self):
                pass
        api = bare_api()
        with mock.patch.object(server, "ThreadingHTTPServer", Capture):
            api._serve_phone_app()
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), got["handler"])
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/index.html", timeout=5) as r:
                self.assertEqual(r.headers.get("Cache-Control"), "no-cache")
        finally:
            httpd.shutdown()


# -- private files: settings, the phone switch, MCP servers (Bearer tokens) ------------------------

class Private(unittest.TestCase):
    def mode(self, path):
        return stat.S_IMODE(path.stat().st_mode)

    def test_modes(self):
        window.SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        window.SETTINGS.write_text("{}")
        window.SETTINGS.chmod(0o644)               # an older install
        window.write_settings(brain="ollama")
        self.assertEqual(self.mode(window.SETTINGS), 0o600)
        api = bare_api()
        api._mcp_write({"s": {"url": "https://example.com", "headers": {"Authorization": "Bearer t"}}})
        self.assertEqual(self.mode(window.SETTINGS.parent / api.MCP_FILE), 0o600)
        with mock.patch.object(window.Api, "_stop_remote"), mock.patch.object(window.Api, "remote_state", return_value={}):
            api.remote_set(False)
        self.assertEqual(self.mode(window.SETTINGS.parent / api.REMOTE_FILE), 0o600)
        self.assertEqual(list(window.SETTINGS.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
