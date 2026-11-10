"""
Group projects: you and your friends put your agents to work on one project.

A project lives in a sealed group (channels.py). Everything about it travels as
small typed messages in that group, and every member rebuilds the same state by
replaying them, in any order (an event log). Nothing in this file talks to the
network or runs an agent: it is the rules, so they can be tested on their own.

Who may do what, checked on every message whoever sent it:
  - any member of the group may start a project and chooses its lead;
  - only the lead plans: proposes tasks and gives each one to a member's agent;
  - only the member a task was given to accepts it, refuses it, or sends its
    result. A friend's agent never runs on your computer: you run your own
    tasks, on your own machine, after saying yes;
  - only the lead closes the project with a synthesis; any member may dissent.
A message that breaks a rule is ignored, and why is kept (`Ledger.rejects`).

The sender of a message is the one the sealed channel authenticated, passed in
by the caller, never a field of the message itself.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path

from . import system

HOME = Path(os.environ.get("ROOT_HARNESS_HOME") or Path.home() / ".root-harness")
FILE = HOME / "projects.json"
VERSION = 1
KINDS = ("project", "roster", "task", "plan", "accept", "refuse", "result", "synthesis", "dissent")

# What a relay comfortably carries in one sealed message, and what a person reads.
MAX = {"title": 120, "goal": 2000, "detail": 2000, "result": 8000, "text": 4000, "reason": 300, "name": 60}
MAX_TASKS = 50
MAX_AGENTS = 20
MAX_PENDING = 500
MAX_REJECTS = 200
ID = re.compile(r"^[A-Za-z0-9_\-:.#@]{1,96}$")

on_change = lambda: None     # the window points this at the sync


def _clean(text, limit: int) -> str:
    """Plain text only: no control characters, trimmed to what a relay carries."""
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(text or ""))
    return s.strip()[:limit]


def _id(value) -> str | None:
    s = str(value or "")
    return s if ID.match(s) else None


def new_id() -> str:
    return secrets.token_hex(8)


def message(kind: str, project: str, **payload) -> dict:
    """A message ready to send in the group. The channel adds who sent it."""
    if kind not in KINDS:
        raise ValueError(f"unknown project message: {kind}")
    return {"rh_project": VERSION, "id": new_id(), "kind": kind, "project": project,
            "at": time.time(), **payload}


def is_project_message(m) -> bool:
    return isinstance(m, dict) and m.get("rh_project") == VERSION and m.get("kind") in KINDS


# A sealed message holds ~64 KB of clear text, wrapped twice: stay well under it.
# Measured in bytes, not characters: accented text weighs more than it looks.
WIRE_BYTES = 30000


def to_wire(m: dict) -> str | None:
    """The text to seal for the group, or None if it is not a project message or too big."""
    if not is_project_message(m):
        return None
    text = json.dumps(m, ensure_ascii=False)
    return text if len(text.encode("utf-8")) <= WIRE_BYTES else None


def from_wire(content) -> dict | None:
    """What a friend sent, if it is a project message of a sane size; None otherwise.
    The rules (who may do what) are checked later by the Ledger, with the real sender."""
    if not isinstance(content, str) or len(content.encode("utf-8")) > WIRE_BYTES:
        return None
    try:
        m = json.loads(content)
    except (ValueError, TypeError):
        return None
    return m if is_project_message(m) and _id(m.get("id")) and _id(m.get("project")) else None


def summary(m: dict) -> str:
    """One readable line for the list of conversations (a project message is JSON)."""
    k = m.get("kind")
    if k == "project":
        return "project: " + _clean(m.get("title"), 80)
    if k == "plan":
        n = len(m.get("tasks") or [])
        return f"project plan: {n} task{'s' if n != 1 else ''}"
    return {"roster": "shared their agents", "task": "project: a new task", "accept": "accepted a task",
            "refuse": "refused a task", "result": "sent a task result", "synthesis": "closed the project",
            "dissent": "disagreed with the project"}.get(k, "project update")


class Wait(Exception):
    """The message depends on one that has not arrived yet (relays do not keep order)."""


class Reject(Exception):
    """The message breaks a rule: it is ignored."""


class Ledger:
    """Every project of a group, rebuilt from its messages."""

    def __init__(self, allowed: set[str] | None = None):
        # The members of the group this ledger belongs to: a project there can only
        # involve them. None means no group around (tests, tools).
        self.allowed = set(allowed) if allowed is not None else None
        self.projects: dict[str, dict] = {}
        self.log: list[dict] = []          # [{"sender", "msg"}] applied, in order
        self.pending: list[dict] = []      # waiting for an earlier message
        self.rejects: list[dict] = []      # ignored, with the reason
        self._seen: set[str] = set()

    # ── reading ──────────────────────────────────────────────────────────
    def project(self, pid: str) -> dict | None:
        return self.projects.get(pid)

    def mine(self, member: str) -> list[dict]:
        """The tasks given to you that wait for your yes or your result."""
        out = []
        for p in self.projects.values():
            if p["status"] != "open":
                continue
            for t in p["tasks"].values():
                if t["member"] == member and t["status"] in ("proposed", "accepted"):
                    out.append({"project": p["id"], "project_title": p["title"], **t})
        return out

    # ── writing ──────────────────────────────────────────────────────────
    def apply(self, msg, sender: str) -> bool:
        """Apply one message from `sender`. True when it changed something now;
        False when it was a repeat, waits for an earlier message, or was refused."""
        sender = _id(sender)
        if not sender or not is_project_message(msg):
            self._reject(msg, sender, "not a project message")
            return False
        mid = _id(msg.get("id"))
        if not mid:
            self._reject(msg, sender, "no message id")
            return False
        if mid in self._seen:
            return False
        try:
            self._apply(msg, sender)
        except Wait:
            if not any(w["msg"].get("id") == mid for w in self.pending):
                self.pending.append({"sender": sender, "msg": msg})
                del self.pending[:-MAX_PENDING]
            return False
        except Reject as e:
            self._seen.add(mid)
            self._reject(msg, sender, str(e))
            return False
        self._seen.add(mid)
        self.log.append({"sender": sender, "msg": msg})
        self._retry()
        return True

    def _retry(self):
        progressed = True
        while progressed and self.pending:
            progressed = False
            for w in list(self.pending):
                try:
                    self._apply(w["msg"], w["sender"])
                except Wait:
                    continue
                except Reject as e:
                    self.pending.remove(w)
                    self._seen.add(w["msg"]["id"])
                    self._reject(w["msg"], w["sender"], str(e))
                    progressed = True
                    continue
                self.pending.remove(w)
                self._seen.add(w["msg"]["id"])
                self.log.append(w)
                progressed = True

    def _reject(self, msg, sender, why: str):
        self.rejects.append({"sender": sender, "id": (msg or {}).get("id") if isinstance(msg, dict) else None,
                             "kind": (msg or {}).get("kind") if isinstance(msg, dict) else None, "why": why})
        del self.rejects[:-MAX_REJECTS]

    def _note(self, p: dict, sender: str, msg: dict, what: str, **extra):
        p["journal"].append({"at": float(msg.get("at") or time.time()), "who": sender,
                             "what": what, **{k: v for k, v in extra.items() if v not in (None, "")}})

    def _apply(self, msg: dict, sender: str):
        kind = msg["kind"]
        pid = _id(msg.get("project"))
        if not pid:
            raise Reject("no project id")
        if kind == "project":
            return self._start(msg, sender, pid)
        p = self.projects.get(pid)
        if p is None:
            raise Wait()
        if sender not in p["members"]:
            raise Reject("sender is not a member of this project")
        if p["status"] != "open" and kind != "dissent":
            raise Reject("the project is closed")
        getattr(self, "_" + kind)(p, msg, sender)

    def _start(self, msg, sender, pid):
        if pid in self.projects:
            raise Reject("this project already exists")
        lead = msg.get("lead") or {}
        lead_member = _id(lead.get("member"))
        members = [m for m in (_id(x) for x in (msg.get("members") or [])) if m]
        if sender not in members:
            members.insert(0, sender)
        members = list(dict.fromkeys(members))[:MAX_AGENTS]
        if self.allowed is not None:
            if sender not in self.allowed:
                raise Reject("the sender is not in this group")
            members = [m for m in members if m in self.allowed]
        if not lead_member or lead_member not in members:
            raise Reject("the lead must be a member of the project")
        title = _clean(msg.get("title"), MAX["title"])
        if not title:
            raise Reject("a project needs a title")
        p = {"id": pid, "title": title, "goal": _clean(msg.get("goal"), MAX["goal"]),
             "by": sender, "members": members,
             "lead": {"member": lead_member, "agent": _clean(lead.get("agent"), MAX["name"])},
             "status": "open", "created": float(msg.get("at") or time.time()),
             "rosters": {}, "tasks": {}, "synthesis": "", "dissents": [], "journal": []}
        self.projects[pid] = p
        self._note(p, sender, msg, "started the project", text=title)

    def _roster(self, p, msg, sender):
        agents = []
        for a in (msg.get("agents") or [])[:MAX_AGENTS]:
            if not isinstance(a, dict):
                continue
            aid = _id(a.get("id"))
            if not aid:
                continue
            forces = [f for f in (_clean(x, 30) for x in (a.get("forces") or [])[:12]) if f]
            agents.append({"id": aid, "name": _clean(a.get("name") or aid, MAX["name"]), "forces": forces})
        p["rosters"][sender] = agents
        self._note(p, sender, msg, "shared their agents", text=", ".join(a["name"] for a in agents))

    def _task(self, p, msg, sender):
        if sender != p["lead"]["member"]:
            raise Reject("only the lead gives tasks")
        t = msg.get("task") or {}
        tid = _id(t.get("id"))
        member = _id(t.get("member"))
        if not tid:
            raise Reject("a task needs an id")
        if tid in p["tasks"]:
            raise Reject("this task already exists")
        if len(p["tasks"]) >= MAX_TASKS:
            raise Reject("too many tasks in this project")
        if member not in p["members"]:
            raise Reject("a task can only go to a member of the project")
        title = _clean(t.get("title"), MAX["title"])
        if not title:
            raise Reject("a task needs a title")
        agent = _clean(t.get("agent"), MAX["name"])
        roster = p["rosters"].get(member)
        if roster is not None and agent and agent not in {a["id"] for a in roster}:
            raise Reject("this member did not share that agent")
        p["tasks"][tid] = {"id": tid, "title": title, "detail": _clean(t.get("detail"), MAX["detail"]),
                           "member": member, "agent": agent, "status": "proposed",
                           "result": "", "reason": "", "at": float(msg.get("at") or time.time())}
        self._note(p, sender, msg, "gave a task", task=tid, text=title, to=member, agent=agent)

    def _plan(self, p, msg, sender):
        """Several tasks in one message: free relays refuse bursts, and a group
        message already goes out once per member."""
        if sender != p["lead"]["member"]:
            raise Reject("only the lead gives tasks")
        tasks = [t for t in (msg.get("tasks") or []) if isinstance(t, dict)][:MAX_TASKS]
        if not tasks:
            raise Reject("an empty plan")
        given = 0
        for t in tasks:
            try:
                self._task(p, {**msg, "task": t}, sender)
                given += 1
            except Reject as e:
                self._reject({**msg, "kind": "task"}, sender, f"{t.get('id')}: {e}")
        if not given:
            raise Reject("no task of this plan could be given")

    def _own_task(self, p, msg, sender) -> dict:
        tid = _id(msg.get("task"))
        t = p["tasks"].get(tid) if tid else None
        if t is None:
            raise Wait()
        if t["member"] != sender:
            raise Reject("only the member this task was given to can answer it")
        return t

    def _accept(self, p, msg, sender):
        t = self._own_task(p, msg, sender)
        if t["status"] != "proposed":
            raise Reject("this task is not waiting for an answer")
        t["status"] = "accepted"
        self._note(p, sender, msg, "accepted a task", task=t["id"], text=t["title"])

    def _refuse(self, p, msg, sender):
        t = self._own_task(p, msg, sender)
        if t["status"] != "proposed":
            raise Reject("this task is not waiting for an answer")
        t["status"] = "refused"
        t["reason"] = _clean(msg.get("reason"), MAX["reason"])
        self._note(p, sender, msg, "refused a task", task=t["id"], text=t["reason"])

    def _result(self, p, msg, sender):
        t = self._own_task(p, msg, sender)
        if t["status"] == "proposed":
            raise Wait()                     # the yes may still be on its way
        if t["status"] != "accepted":
            raise Reject("this task is not running")
        ok = bool(msg.get("ok", True))
        t["status"] = "done" if ok else "failed"
        t["result"] = _clean(msg.get("text"), MAX["result"])
        self._note(p, sender, msg, "finished a task" if ok else "could not finish a task",
                   task=t["id"], agent=t["agent"], text=t["result"][:200])

    def _synthesis(self, p, msg, sender):
        if sender != p["lead"]["member"]:
            raise Reject("only the lead closes the project")
        p["synthesis"] = _clean(msg.get("text"), MAX["text"])
        p["status"] = "closed"
        self._note(p, sender, msg, "closed the project", text=p["synthesis"][:200])

    def _dissent(self, p, msg, sender):
        text = _clean(msg.get("text"), MAX["reason"])
        if not text:
            raise Reject("a dissent says why")
        p["dissents"].append({"who": sender, "text": text})
        self._note(p, sender, msg, "disagreed", text=text)

    # ── saving ───────────────────────────────────────────────────────────
    def dump(self) -> dict:
        return {"version": VERSION, "log": self.log, "pending": self.pending}

    @classmethod
    def load(cls, data: dict, allowed: set[str] | None = None) -> "Ledger":
        led = cls(allowed)
        for w in sorted((data or {}).get("log", []) + (data or {}).get("pending", []),
                        key=lambda w: (float(w["msg"].get("at") or 0), str(w["msg"].get("id")))):
            led.apply(w.get("msg"), w.get("sender"))
        return led


def progress(p: dict) -> dict:
    """Where a project stands, for the follow-up view."""
    tasks = list(p["tasks"].values())
    count = lambda s: sum(t["status"] == s for t in tasks)
    finished = count("done") + count("failed") + count("refused")
    return {"total": len(tasks), "done": count("done"), "failed": count("failed"),
            "refused": count("refused"), "waiting": count("proposed"), "running": count("accepted"),
            "percent": round(100 * finished / len(tasks)) if tasks else 0}


def cast(subtasks: list[dict], rosters: dict[str, list[dict]], first: int = 1) -> list[dict]:
    """Give each subtask to the agent of a member best at it, fairly and always the same way.

    `subtasks`: [{"title", "detail", "needs": [tags]}]; `rosters`: {member: [{"id", "forces"}]}.
    The score is how many of the needed tags the agent's forces cover. At equal score the
    least loaded member wins (nobody gets everything), then the order of the rosters.
    `first`: number of the first task, after the ones the project already has."""
    seats = [(m, a) for m, agents in rosters.items() for a in agents]
    if not seats:
        raise ValueError("nobody shared an agent yet")
    load = {m: 0 for m in rosters}
    out = []
    for i, st in enumerate(subtasks):
        needs = [str(n).lower() for n in (st.get("needs") or [])]

        def score(seat):
            forces = " ".join(seat[1].get("forces") or []).lower()
            return sum(n in forces for n in needs)

        member, agent = max(seats, key=lambda s: (score(s), -load[s[0]]))
        load[member] += 1
        out.append({"id": f"t{first + i}", "title": st.get("title", ""), "detail": st.get("detail", ""),
                    "member": member, "agent": agent["id"]})
    return out


# ── on disk: one ledger per group, sealed with the rest of your memory ──────
def _read() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ledger(group: str, allowed: set[str] | None = None) -> Ledger:
    return Ledger.load(_read().get(group) or {}, allowed)


def save(group: str, led: Ledger) -> None:
    data = _read()
    data[group] = led.dump()
    system.atomic_write(FILE, json.dumps(data, ensure_ascii=False), private=True)
    on_change()
