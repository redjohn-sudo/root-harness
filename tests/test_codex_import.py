"""Imports past Codex conversations from the CLI's rollout files: the parser
keeps what you typed and what Codex answered, drops the injected AGENTS.md and
command wrappers, and the first real prompt becomes the title. Codex cannot
resume its own thread, so the imported history rides along as a preamble on the
first turn of a fresh thread."""
import itertools
import json
import tempfile
import unittest
from pathlib import Path

from rootharness import codex_sessions, bridge_codex


ROLLOUT = [
    {"type": "session_meta", "payload": {"session_id": "abc123", "cwd": "/home"}},
    {"type": "event_msg", "payload": {"type": "task_started"}},
    {"type": "response_item", "payload": {"type": "message", "role": "developer",
                                          "content": [{"type": "input_text", "text": "system rules"}]}},
    {"type": "response_item", "payload": {"type": "message", "role": "user",
                                          "content": [{"type": "input_text", "text": "# AGENTS.md instructions\nblah"}]}},
    {"type": "response_item", "payload": {"type": "message", "role": "user",
                                          "content": [{"type": "input_text", "text": "<command-name>/clear</command-name>"}]}},
    {"type": "response_item", "payload": {"type": "message", "role": "user",
                                          "content": [{"type": "input_text", "text": "fix the parser please"}]}},
    {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                          "content": [{"type": "output_text", "text": "Done, here it is."}]}},
    {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "input": "ls -la"}},
]


class CodexParser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name) / "2026" / "10" / "30"
        d.mkdir(parents=True)
        (d / "rollout-2026-10-30T00-00-00-abc123.jsonl").write_text(
            "\n".join(json.dumps(o) for o in ROLLOUT), encoding="utf-8")
        self._orig = codex_sessions.SESSIONS
        codex_sessions.SESSIONS = Path(self.tmp.name)

    def tearDown(self):
        codex_sessions.SESSIONS = self._orig
        self.tmp.cleanup()

    def test_lists_with_real_prompt_as_title(self):
        sessions = codex_sessions.list_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].session_id, "abc123")
        self.assertEqual(sessions[0].title, "fix the parser please")

    def test_events_keep_mine_and_drop_injected(self):
        ev = codex_sessions.events("abc123")
        kinds = [(e["type"], e.get("text", e.get("name"))) for e in ev]
        self.assertIn(("user", "fix the parser please"), kinds)
        self.assertIn(("text", "Done, here it is."), kinds)
        self.assertIn(("tool", "exec"), kinds)
        # the developer rules, the AGENTS.md preamble and the /clear wrapper are gone
        self.assertNotIn("user", [k for k, v in kinds if v and "AGENTS" in str(v)])
        self.assertFalse(any("system rules" in str(v) for _, v in kinds))
        self.assertFalse(any("command-name" in str(v) for _, v in kinds))


class FakeProc:
    def __init__(self):
        self.written = []
        self.stdin = self
        self.stdout = self
        self._replies = [json.dumps({"method": "turn/completed", "params": {}}) + "\n"]

    def write(self, s):
        self.written.append(s)

    def flush(self):
        pass

    def readline(self):
        return self._replies.pop(0) if self._replies else ""

    def poll(self):
        return None


class CodexPreamble(unittest.TestCase):
    def test_imported_history_prepended_once(self):
        s = bridge_codex.Session.__new__(bridge_codex.Session)
        s.model = s.effort = None
        s.thread = "t1"
        s.preamble = "EARLIER CONVERSATION\n\n"
        s._ids = itertools.count(1)
        s.proc = FakeProc()
        s._ensure = lambda: None
        s.run_turn("my new question", lambda e: None)
        sent = [json.loads(w) for w in s.proc.written]
        start = next(m for m in sent if m.get("method") == "turn/start")
        text = next(i["text"] for i in start["params"]["input"] if i["type"] == "text")
        self.assertTrue(text.startswith("EARLIER CONVERSATION"))
        self.assertIn("my new question", text)
        self.assertEqual(s.preamble, "")       # sent once, then cleared


if __name__ == "__main__":
    unittest.main()
