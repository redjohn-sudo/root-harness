"""A tiny MCP server over streamable HTTP, for the remote-transport test.

Run on its own: `python tests/mcp_http_demo_server.py 8777` serves MCP at
http://127.0.0.1:8777/mcp. No API key, touches nothing. Key-less, for the demo.
"""
import sys

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

mcp = MCPServer("rootharness-http-demo")


@mcp.tool(description="Add two integers and return the sum.")
def add(a: int, b: int) -> int:
    return a + b


@mcp.tool(description="Return the given text in upper case.",
          annotations=ToolAnnotations(readOnlyHint=True))
def shout(text: str) -> str:
    return text.upper()


if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=int(sys.argv[1]))
