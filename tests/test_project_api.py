"""The window side of group projects, without relays nor real agents: what is
sent and when, what a friend's message does, running a task you accepted.
Run:  .venv/bin/python -m unittest tests/test_project_api.py"""
import json
import os
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

os.environ.setdefault("ROOT_HARNESS_HOME", tempfile.mkdtemp(prefix="rh-test-"))

from rootharness import window, projects, brains, conversations, channels   # noqa: E402  (after the home is set)

ME, FRIEND, OTHER = "a" * 64, "b" * 64, "e" * 64
THREADED = window._background          # the real one: sends to the relays in a thread


def setUpModule():
    window._background = lambda fn: fn()   # inline, so tests see the send at once


def tearDownModule():
    window._background = THREADED


class FakeChannels:
    def __init__(self):
        self.me, self.sent = ME, []

    def send_project(self, cid, msg):
        self.sent.append((cid, msg))
        return {"relays_ok": 2}

    def _name(self, h, s=None):
        return "You" if h == ME else "friend"


def api_with_group(request=False):
    api = object.__new__(window.Api)
    api._busy, api._pending, api._next = threading.Lock(), {}, 0
    api.conv, api.log, api._window, api.remote = None, {"events": []}, None, None
    api.keys = object()
    api.channels = FakeChannels()
    api.brain = {"id": "claude", "kind": "claude", "name": "Claude"}
    api.session = types.SimpleNamespace(model=None)
    api.events = []
    api._emit = api.events.append
    api._making = threading.Lock()
    cid = "g" + os.urandom(6).hex()
    groups = {"channels": {cid: {"name": "hackathon", "members": [FRIEND], "request": request}}}
    patch = mock.patch.object(channels, "_load", return_value=groups)
    patch.start()
    return api, cid, patch


def friend_says(api, cid, msg, sender=FRIEND):
    api._project_in({"type": "project_message", "channel": cid, "sender": sender,
                     "members": sorted({ME, FRIEND}), "project": msg})


class Sending(unittest.TestCase):
    def setUp(self):
        self.api, self.cid, self.patch = api_with_group()

    def tearDown(self):
        self.patch.stop()

    def test_creating_a_project_records_it_and_sends_it_once(self):
        r = self.api.project_create(self.cid, "Landing page", "for the hackathon")
        self.assertTrue(r["ok"])
        self.assertEqual(len(self.api.channels.sent), 1)
        listed = self.api.projects_list()["projects"]
        self.assertEqual([p["title"] for p in listed], ["Landing page"])
        self.assertTrue(listed[0]["i_lead"])
        self.assertEqual(sorted(listed[0]["members"]), sorted([ME, FRIEND]))

    def test_a_click_never_waits_for_the_relays(self):
        def slow(cid, msg):
            time.sleep(1.0)
            return {"relays_ok": 1}
        self.api.channels.send_project = slow
        with mock.patch.object(window, "_background", THREADED):
            t0 = time.time()
            r = self.api.project_create(self.cid, "Fast")
            took = time.time() - t0
        self.assertTrue(r["ok"])
        self.assertLess(took, 0.3)
        self.assertEqual([p["title"] for p in self.api.projects_list()["projects"]], ["Fast"])   # shown at once

    def test_when_no_relay_takes_it_you_are_told(self):
        self.api.channels.send_project = lambda cid, msg: {"relays_ok": 0}
        self.assertTrue(self.api.project_create(self.cid, "Offline")["ok"])
        self.assertTrue(any(e.get("type") == "project_send_failed" for e in self.api.events))

    def test_a_refused_message_is_not_sent(self):
        r = self.api.project_create(self.cid, "")            # a project needs a title
        self.assertIn("error", r)
        self.assertEqual(self.api.channels.sent, [])

    def test_only_the_lead_sends_a_plan(self):
        start = projects.message("project", "p1", title="X", lead={"member": FRIEND}, members=[ME, FRIEND])
        friend_says(self.api, self.cid, start)
        r = self.api.project_send_plan(self.cid, "p1", [{"id": "t1", "title": "a", "member": FRIEND}])
        self.assertIn("only the lead", r["error"])
        self.assertEqual(self.api.channels.sent, [])

    def test_a_group_you_did_not_accept_takes_no_project(self):
        self.patch.stop()
        api, cid, self.patch = api_with_group(request=True)
        with self.assertRaises(ValueError):
            api.project_create(cid, "X")


class FromFriends(unittest.TestCase):
    def setUp(self):
        self.api, self.cid, self.patch = api_with_group()
        friend_says(self.api, self.cid, projects.message("project", "p1", title="Site", lead={"member": FRIEND},
                                                         members=[ME, FRIEND]))

    def tearDown(self):
        self.patch.stop()

    def test_a_task_given_to_me_waits_for_my_yes(self):
        friend_says(self.api, self.cid, projects.message("plan", "p1", tasks=[{"id": "t1", "title": "Copy", "member": ME}]))
        mine = self.api.projects_list()["mine"]
        self.assertEqual([(t["id"], t["status"]) for t in mine], [("t1", "proposed")])
        self.assertIn({"type": "projects_changed", "channel": self.cid}, self.api.events)

    def test_someone_outside_the_group_counts_for_nothing(self):
        friend_says(self.api, self.cid, projects.message("plan", "p1", tasks=[{"id": "t9", "title": "x", "member": ME}]),
                    sender=OTHER)
        self.assertEqual(self.api.projects_list()["mine"], [])


class RunningATask(unittest.TestCase):
    def setUp(self):
        self.api, self.cid, self.patch = api_with_group()
        friend_says(self.api, self.cid, projects.message("project", "p1", title="Site", lead={"member": FRIEND},
                                                         members=[ME, FRIEND]))
        friend_says(self.api, self.cid, projects.message("plan", "p1", tasks=[
            {"id": "t1", "title": "Write the copy", "detail": "three lines", "member": ME},
            {"id": "t2", "title": "Design", "member": FRIEND}]))

    def tearDown(self):
        self.patch.stop()

    def test_not_yours_not_accepted_or_busy_never_runs(self):
        self.assertIn("someone else", self.api.project_run_task(self.cid, "p1", "t2")["error"])
        self.assertIn("Accept", self.api.project_run_task(self.cid, "p1", "t1")["error"])
        self.api.project_answer(self.cid, "p1", "t1", True)
        self.api._busy.acquire()
        try:
            self.assertIn("busy", self.api.project_run_task(self.cid, "p1", "t1")["error"])
        finally:
            self.api._busy.release()

    def test_it_runs_in_its_own_session_and_the_report_waits_for_my_click(self):
        self.api.project_answer(self.cid, "p1", "t1", True)
        sent_before = len(self.api.channels.sent)
        seen = {}

        class Session:
            model = effort = None

            def run_turn(self, prompt, emit):
                seen["prompt"] = prompt
                emit({"type": "text", "text": "Working on it."})
                emit({"type": "text", "text": "Done: copy written in copy.md."})
                emit({"type": "done", "text": ""})

            def close(self):
                seen["closed"] = True
        with mock.patch.object(brains, "new_session", return_value=Session()), \
                mock.patch.object(brains, "catalog", return_value=[]), \
                mock.patch.object(conversations, "create", return_value="c-proj"), \
                mock.patch.object(conversations, "write_log"):
            self.assertTrue(self.api.project_run_task(self.cid, "p1", "t1")["ok"])
            for _ in range(200):
                if any(e.get("type") == "project_task_done" for e in self.api.events):
                    break
                time.sleep(0.01)
        done = next(e for e in self.api.events if e.get("type") == "project_task_done")
        self.assertEqual(done["text"], "Done: copy written in copy.md.")
        self.assertIn("comes from a friend", seen["prompt"])          # the agent knows where the task comes from
        self.assertTrue(seen["closed"])
        self.assertEqual(self.api.log["events"], [])                   # your own conversation is untouched
        self.assertEqual(len(self.api.channels.sent), sent_before)     # nothing sent until you click
        self.assertFalse(self.api._busy.locked())


class Planning(unittest.TestCase):
    def setUp(self):
        self.api, self.cid, self.patch = api_with_group()
        self.api.project_create(self.cid, "Site")
        self.pid = self.api.channels.sent[-1][1]["project"]

    def tearDown(self):
        self.patch.stop()

    def test_the_lead_gets_a_draft_to_review_nothing_is_sent(self):
        friend_says(self.api, self.cid, projects.message("roster", self.pid, agents=[{"id": "kimi", "forces": ["critique"]}]))
        projects_led_before = len(self.api.channels.sent)
        answer = json.dumps([{"title": "Review the copy", "detail": "be harsh", "needs": ["critique"]}])
        with mock.patch("rootharness.side.ask", return_value=answer):
            r = self.api.project_plan_draft(self.cid, self.pid)
        self.assertEqual([(t["title"], t["member"], t["agent"]) for t in r["tasks"]], [("Review the copy", FRIEND, "kimi")])
        self.assertEqual(len(self.api.channels.sent), projects_led_before)

    def test_no_agents_shared_yet(self):
        self.assertIn("share their agents", self.api.project_plan_draft(self.cid, self.pid)["error"])


if __name__ == "__main__":
    unittest.main()
