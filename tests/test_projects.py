"""Group projects, without relays nor agents: the rules of who may do what,
messages arriving in any order, the fair casting, the follow-up, saving.
Run:  .venv/bin/python -m unittest tests/test_projects.py"""
import os
import tempfile
import unittest
from pathlib import Path

os.environ["ROOT_HARNESS_HOME"] = tempfile.mkdtemp(prefix="rh-test-")
HOME = Path(os.environ["ROOT_HARNESS_HOME"])

from rootharness import projects as pj   # noqa: E402  (after the home is set)

ME, ALICE, BOB, EVE = "me#aaaa", "alice#bbbb", "bob#cccc", "eve#dddd"


def start(led, pid="p1", lead=ME, members=(ME, ALICE, BOB), sender=ME):
    m = pj.message("project", pid, title="Build a landing page", goal="A page for our hackathon",
                   lead={"member": lead, "agent": "claude"}, members=list(members))
    return led.apply(m, sender), m


def task(pid, tid, member, agent="claude", title="Write the copy"):
    return pj.message("task", pid, task={"id": tid, "title": title, "member": member, "agent": agent})


class Lifecycle(unittest.TestCase):
    def test_a_project_from_start_to_close(self):
        led = pj.Ledger()
        self.assertTrue(start(led)[0])
        self.assertTrue(led.apply(task("p1", "t1", ALICE), ME))
        self.assertTrue(led.apply(pj.message("accept", "p1", task="t1"), ALICE))
        self.assertTrue(led.apply(pj.message("result", "p1", task="t1", ok=True, text="Copy written."), ALICE))
        p = led.project("p1")
        self.assertEqual(p["tasks"]["t1"]["status"], "done")
        self.assertEqual(pj.progress(p)["percent"], 100)
        self.assertTrue(led.apply(pj.message("synthesis", "p1", text="Shipped."), ME))
        self.assertEqual(p["status"], "closed")
        whats = [e["what"] for e in p["journal"]]
        self.assertEqual(whats, ["started the project", "gave a task", "accepted a task",
                                 "finished a task", "closed the project"])

    def test_my_tasks_waiting_for_me(self):
        led = pj.Ledger()
        start(led)
        led.apply(task("p1", "t1", ALICE), ME)
        led.apply(task("p1", "t2", BOB), ME)
        self.assertEqual([t["id"] for t in led.mine(ALICE)], ["t1"])
        led.apply(pj.message("refuse", "p1", task="t1", reason="no time"), ALICE)
        self.assertEqual(led.mine(ALICE), [])
        self.assertEqual(led.project("p1")["tasks"]["t1"]["reason"], "no time")


class Rules(unittest.TestCase):
    """The safety rules: whoever sends a message, it only counts if allowed."""

    def setUp(self):
        self.led = pj.Ledger()
        start(self.led)
        self.led.apply(task("p1", "t1", ALICE), ME)

    def test_only_the_lead_gives_tasks(self):
        self.assertFalse(self.led.apply(task("p1", "t2", BOB), ALICE))
        self.assertNotIn("t2", self.led.project("p1")["tasks"])
        self.assertIn("only the lead", self.led.rejects[-1]["why"])

    def test_a_friend_cannot_answer_your_task(self):
        self.assertFalse(self.led.apply(pj.message("accept", "p1", task="t1"), BOB))
        self.assertEqual(self.led.project("p1")["tasks"]["t1"]["status"], "proposed")

    def test_a_friend_cannot_finish_your_task(self):
        self.led.apply(pj.message("accept", "p1", task="t1"), ALICE)
        self.assertFalse(self.led.apply(pj.message("result", "p1", task="t1", text="fake"), BOB))
        self.assertEqual(self.led.project("p1")["tasks"]["t1"]["status"], "accepted")

    def test_even_the_lead_cannot_finish_your_task(self):
        self.led.apply(pj.message("accept", "p1", task="t1"), ALICE)
        self.assertFalse(self.led.apply(pj.message("result", "p1", task="t1", text="fake"), ME))

    def test_a_stranger_counts_for_nothing(self):
        self.assertFalse(self.led.apply(pj.message("dissent", "p1", text="hello"), EVE))
        self.assertFalse(self.led.apply(task("p1", "t9", EVE), ME))   # cannot be given a task either

    def test_only_the_lead_closes(self):
        self.assertFalse(self.led.apply(pj.message("synthesis", "p1", text="done"), ALICE))
        self.assertEqual(self.led.project("p1")["status"], "open")

    def test_the_sender_field_of_a_message_is_never_trusted(self):
        forged = pj.message("task", "p1", task={"id": "t3", "title": "x", "member": BOB}, sender=ME, **{"from": ME})
        self.assertFalse(self.led.apply(forged, ALICE))   # it is Alice who really sent it

    def test_the_lead_must_be_a_member(self):
        led = pj.Ledger()
        ok, _ = start(led, pid="p2", lead=EVE, members=(ME, ALICE))
        self.assertFalse(ok)

    def test_a_task_only_goes_to_an_agent_the_member_shared(self):
        self.led.apply(pj.message("roster", "p1", agents=[{"id": "codex", "name": "Codex", "forces": ["code"]}]), BOB)
        self.assertFalse(self.led.apply(task("p1", "t4", BOB, agent="claude"), ME))
        self.assertTrue(self.led.apply(task("p1", "t5", BOB, agent="codex"), ME))

    def test_a_project_only_involves_members_of_its_group(self):
        led = pj.Ledger(allowed={ME, ALICE})
        ok, _ = start(led, pid="p3", members=(ME, ALICE, EVE))
        self.assertTrue(ok)
        self.assertEqual(led.project("p3")["members"], [ME, ALICE])     # Eve is not in this group
        outsider = pj.Ledger(allowed={ME, ALICE})
        self.assertFalse(start(outsider, pid="p4", lead=EVE, members=(EVE,), sender=EVE)[0])

    def test_a_closed_project_takes_no_more_work(self):
        self.led.apply(pj.message("synthesis", "p1", text="done"), ME)
        self.assertFalse(self.led.apply(task("p1", "t6", BOB), ME))
        self.assertTrue(self.led.apply(pj.message("dissent", "p1", text="not finished"), BOB))


class Plan(unittest.TestCase):
    def test_one_message_gives_several_tasks(self):
        led = pj.Ledger()
        start(led)
        plan = pj.message("plan", "p1", tasks=[{"id": "t1", "title": "Copy", "member": ALICE},
                                              {"id": "t2", "title": "Design", "member": BOB},
                                              {"id": "t3", "title": "Spy", "member": EVE}])
        self.assertTrue(led.apply(plan, ME))
        self.assertEqual(sorted(led.project("p1")["tasks"]), ["t1", "t2"])   # Eve is not a member
        self.assertTrue(any("t3" in r["why"] for r in led.rejects))

    def test_only_the_lead_sends_a_plan(self):
        led = pj.Ledger()
        start(led)
        self.assertFalse(led.apply(pj.message("plan", "p1", tasks=[{"id": "t1", "title": "x", "member": BOB}]), ALICE))

    def test_the_casting_feeds_a_plan(self):
        led = pj.Ledger()
        start(led)
        rosters = {ALICE: [{"id": "kimi", "forces": ["critique"]}], BOB: [{"id": "glm", "forces": ["code"]}]}
        for m, agents in rosters.items():
            led.apply(pj.message("roster", "p1", agents=agents), m)
        tasks = pj.cast([{"title": "Review", "needs": ["critique"]}, {"title": "Build", "needs": ["code"]}], rosters)
        self.assertTrue(led.apply(pj.message("plan", "p1", tasks=tasks), ME))
        given = {t["title"]: (t["member"], t["agent"]) for t in led.project("p1")["tasks"].values()}
        self.assertEqual(given, {"Review": (ALICE, "kimi"), "Build": (BOB, "glm")})


class Order(unittest.TestCase):
    """Relays keep no order and may deliver twice."""

    def test_a_task_before_its_project_waits_then_lands(self):
        led = pj.Ledger()
        early = task("p1", "t1", ALICE)
        self.assertFalse(led.apply(early, ME))
        self.assertEqual(len(led.pending), 1)
        start(led)
        self.assertEqual(led.pending, [])
        self.assertIn("t1", led.project("p1")["tasks"])

    def test_a_result_before_the_yes_waits(self):
        led = pj.Ledger()
        start(led)
        led.apply(task("p1", "t1", ALICE), ME)
        res = pj.message("result", "p1", task="t1", text="ok")
        self.assertFalse(led.apply(res, ALICE))
        led.apply(pj.message("accept", "p1", task="t1"), ALICE)
        self.assertEqual(led.project("p1")["tasks"]["t1"]["status"], "done")

    def test_the_same_message_twice_counts_once(self):
        led = pj.Ledger()
        start(led)
        m = task("p1", "t1", ALICE)
        self.assertTrue(led.apply(m, ME))
        self.assertFalse(led.apply(m, ME))
        self.assertEqual(len(led.project("p1")["journal"]), 2)

    def test_garbage_is_ignored_quietly(self):
        led = pj.Ledger()
        for junk in (None, "text", {"rh_project": 99}, {"rh_project": 1, "kind": "boom"}, {"rh_project": 1, "kind": "task"}):
            self.assertFalse(led.apply(junk, ME))
        self.assertEqual(led.projects, {})


class Limits(unittest.TestCase):
    def test_texts_are_cleaned_and_capped(self):
        led = pj.Ledger()
        m = pj.message("project", "p1", title="A\x00B" + "x" * 500, lead={"member": ME}, members=[ME])
        led.apply(m, ME)
        t = led.project("p1")["title"]
        self.assertNotIn("\x00", t)
        self.assertLessEqual(len(t), pj.MAX["title"])


class Casting(unittest.TestCase):
    ROSTERS = {ME: [{"id": "claude", "forces": ["synthesis", "code"]}],
               ALICE: [{"id": "kimi", "forces": ["code review", "critique"]}],
               BOB: [{"id": "glm", "forces": ["code", "fast"]}]}

    def test_each_subtask_goes_to_the_best_agent(self):
        out = pj.cast([{"title": "Review", "needs": ["critique"]}], self.ROSTERS)
        self.assertEqual((out[0]["member"], out[0]["agent"]), (ALICE, "kimi"))

    def test_fair_at_equal_strength(self):
        out = pj.cast([{"title": "A", "needs": ["code"]}, {"title": "B", "needs": ["code"]}], self.ROSTERS)
        self.assertNotEqual(out[0]["member"], out[1]["member"])

    def test_always_the_same(self):
        st = [{"title": "A", "needs": ["code"]}, {"title": "B", "needs": ["fast"]}]
        self.assertEqual(pj.cast(st, self.ROSTERS), pj.cast(st, self.ROSTERS))

    def test_a_second_plan_does_not_reuse_task_ids(self):
        first = pj.cast([{"title": "A"}, {"title": "B"}], self.ROSTERS)
        second = pj.cast([{"title": "C"}], self.ROSTERS, first=len(first) + 1)
        self.assertEqual([t["id"] for t in first + second], ["t1", "t2", "t3"])

    def test_nobody_shared_an_agent(self):
        with self.assertRaises(ValueError):
            pj.cast([{"title": "A"}], {})


class Saving(unittest.TestCase):
    def test_a_group_ledger_survives_a_restart(self):
        led = pj.Ledger()
        start(led)
        led.apply(task("p1", "t1", ALICE), ME)
        led.apply(pj.message("accept", "p1", task="t1"), ALICE)
        pj.save("group-1", led)
        again = pj.ledger("group-1")
        self.assertEqual(again.project("p1")["tasks"]["t1"]["status"], "accepted")
        self.assertEqual(pj.ledger("another-group").projects, {})
        self.assertEqual(oct(pj.FILE.stat().st_mode & 0o777), "0o600")


if __name__ == "__main__":
    unittest.main()
