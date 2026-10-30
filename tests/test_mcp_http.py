"""Remote MCP server over HTTP: the same path works for a hosted server.

Starts the HTTP demo server on a free port, connects root-harness to it by URL,
and checks the tools arrive and run just like a local stdio server. (OAuth
refresh for long-lived remote sessions is the next step, not covered here.)
"""
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from rootharness import mcp_tools, permissions, tools

SERVER = str(Path(__file__).parent / "mcp_http_demo_server.py")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def remote():
    port = _free_port()
    proc = subprocess.Popen([sys.executable, SERVER, str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/mcp"
    permissions.set_asker(lambda title, args: True)
    added = None
    for _ in range(40):                          # wait up to ~10s for it to come up
        r = mcp_tools.add_server("remote", url=url)
        if r["ok"]:
            added = r
            break
        time.sleep(0.25)
    yield url, added
    mcp_tools.unload()
    permissions.set_asker(lambda title, args: False)
    proc.terminate()
    try:
        proc.wait(5)
    except Exception:                            # noqa: BLE001
        proc.kill()


def test_remote_http_server_tools_work(remote):
    url, added = remote
    assert added and added["ok"], "the HTTP server did not come up"
    assert set(added["tools"]) == {"add", "shout"}
    assert "remote__add" in tools.REGISTRY
    assert "5" in tools.run("remote__add", {"a": 2, "b": 3})
    # annotations travel over HTTP too
    assert tools.REGISTRY["remote__shout"]["kind"] == permissions.READ_ONLY
