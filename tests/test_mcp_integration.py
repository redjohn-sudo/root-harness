"""The MCP bridge: connect to a server, and every brain gets its tools.

Proves the whole path on the demo server:
  load  ->  tools land in the registry  ->  the OpenAI-format bridge (the one
  DeepSeek / Kimi / GLM / Ollama use) exposes them  ->  running a tool goes
  through the permission gate and returns the server's answer.
"""
import sys
from pathlib import Path

import pytest

from rootharness import bridge_api, mcp_tools, permissions, tools

SERVER = str(Path(__file__).parent / "mcp_demo_server.py")


@pytest.fixture
def demo():
    permissions.set_asker(lambda title, args: True)   # auto-allow in the test
    added = mcp_tools.load({"demo": {"command": sys.executable, "args": [SERVER]}})
    yield added
    mcp_tools.unload()
    permissions.set_asker(lambda title, args: False)   # back to deny-by-default


def test_tools_are_discovered_and_registered(demo):
    assert any(n == "demo__add" for n in demo)
    assert any(n == "demo__shout" for n in demo)
    assert "demo__add" in tools.REGISTRY
    assert tools.REGISTRY["demo__add"]["kind"] == permissions.NEEDS_OK
    assert tools.REGISTRY["demo__add"]["schema"] == {"a": int, "b": int}


def test_non_claude_brains_see_the_tools(demo):
    names = [s["function"]["name"] for s in bridge_api.tool_specs()]
    assert "demo__add" in names
    spec = next(s for s in bridge_api.tool_specs() if s["function"]["name"] == "demo__add")
    assert spec["function"]["parameters"]["properties"]["a"]["type"] == "integer"


def test_running_a_tool_returns_the_server_answer(demo):
    assert "5" in tools.run("demo__add", {"a": 2, "b": 3})
    assert tools.run("demo__shout", {"text": "hello"}).strip() == "HELLO"


def test_read_only_annotation_sets_the_permission_level(demo):
    # the server marks `shout` read-only -> no card; `add` is not -> asks first
    assert tools.REGISTRY["demo__shout"]["kind"] == permissions.READ_ONLY
    assert tools.REGISTRY["demo__add"]["kind"] == permissions.NEEDS_OK
    permissions.set_asker(lambda title, args: False)   # deny everything
    assert tools.run("demo__shout", {"text": "hi"}).strip() == "HI"   # still runs
    assert tools.run("demo__add", {"a": 1, "b": 1}) == "Denied by the user."


def test_permission_gate_blocks_a_denied_tool():
    permissions.set_asker(lambda title, args: True)
    mcp_tools.load({"demo": {"command": sys.executable, "args": [SERVER]}})
    try:
        permissions.set_asker(lambda title, args: False)   # user says no
        assert tools.run("demo__add", {"a": 1, "b": 1}) == "Denied by the user."
    finally:
        mcp_tools.unload()
        permissions.set_asker(lambda title, args: False)


def test_deny_list_leaves_a_tool_out():
    permissions.set_asker(lambda title, args: True)
    r = mcp_tools.add_server("demo", sys.executable, [SERVER], deny=["add"])
    try:
        assert "shout" in r["tools"]
        assert "add" not in r["tools"]
        assert "demo__add" not in tools.REGISTRY     # blocked, never registered
        assert "demo__shout" in tools.REGISTRY
    finally:
        mcp_tools.unload()
        permissions.set_asker(lambda title, args: False)


async def _kill(task):
    task.cancel()
    try:
        await task
    except BaseException:                            # noqa: BLE001
        pass


def test_a_dropped_server_reconnects_and_the_call_succeeds():
    permissions.set_asker(lambda title, args: True)
    mcp_tools.add_server("demo", sys.executable, [SERVER])
    try:
        # simulate a drop: cancel the owner task (its stdio context closes in-task)
        info = mcp_tools._servers["demo"]
        mcp_tools._submit(_kill(info["task"]))
        assert info["task"].done()
        # the tool call should notice the dead task, reconnect, and still answer
        assert "4" in tools.run("demo__add", {"a": 2, "b": 2})
    finally:
        mcp_tools.unload()
        permissions.set_asker(lambda title, args: False)


def test_concurrent_calls_to_one_server_are_safe():
    # stdio cannot be touched from several tasks at once; the owner task
    # serialises the calls, so parallel callers must all get correct answers.
    import threading
    permissions.set_asker(lambda title, args: True)
    mcp_tools.add_server("demo", sys.executable, [SERVER])
    results: dict[int, str] = {}

    def call(i):
        results[i] = tools.run("demo__add", {"a": i, "b": 1})

    try:
        threads = [threading.Thread(target=call, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for i in range(8):
            assert str(i + 1) in results[i], (i, results[i])
    finally:
        mcp_tools.unload()
        permissions.set_asker(lambda title, args: False)


def test_find_tools_discovers_mcp_tools(demo):
    hits = mcp_tools.search("upper")
    assert "demo__shout" in [h["name"] for h in hits]     # shout's desc: "upper case"
    assert tools.REGISTRY["find_tools"]["kind"] == permissions.READ_ONLY
    out = tools.run("find_tools", {"query": "sum"})        # add's desc: "the sum"
    assert "demo__add" in out


def test_unload_removes_the_tools():
    permissions.set_asker(lambda title, args: True)
    mcp_tools.load({"demo": {"command": sys.executable, "args": [SERVER]}})
    assert "demo__add" in tools.REGISTRY
    mcp_tools.unload()
    assert "demo__add" not in tools.REGISTRY
    permissions.set_asker(lambda title, args: False)
