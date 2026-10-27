"""Locks the in-app agent's guardrails: it must never bypass the per-tool
confirmation, and never drive the browser or the computer. These are the two
holes that let injected content open a shopping page on its own."""
import asyncio
import unittest

from rootharness import bridge_claude


class FakeDeny:
    def __init__(self, message=""):
        self.message = message


class FakeAllow:
    def __init__(self, updated_input=None):
        self.updated_input = updated_input


class GardeAgent(unittest.TestCase):
    def setUp(self):
        # a Session without connecting to a real Claude process
        self.s = bridge_claude.Session.__new__(bridge_claude.Session)

    def _decide(self, name, args=None):
        # stub the SDK so _can_use_tool can build its result objects offline
        import sys, types
        fake = types.SimpleNamespace(PermissionResultDeny=FakeDeny, PermissionResultAllow=FakeAllow)
        orig = sys.modules.get("claude_agent_sdk")
        sys.modules["claude_agent_sdk"] = fake
        try:
            return asyncio.run(self.s._can_use_tool(name, args or {}, None))
        finally:
            if orig is not None:
                sys.modules["claude_agent_sdk"] = orig
            else:
                del sys.modules["claude_agent_sdk"]

    def test_no_auto_mode(self):
        # "auto" would bypass the confirmation card entirely
        self.assertNotIn("auto", bridge_claude.MODES)

    def test_set_mode_rejects_auto(self):
        self.s.mode = "default"
        self.s.client = None
        self.s.set_mode("auto")
        self.assertEqual(self.s.mode, "default")

    def test_browser_and_computer_tools_denied(self):
        for name in ("mcp__claude-in-chrome__navigate",
                     "mcp__claude-in-chrome__computer",
                     "computer"):
            with self.subTest(tool=name):
                self.assertIsInstance(self._decide(name), FakeDeny)


if __name__ == "__main__":
    unittest.main()
