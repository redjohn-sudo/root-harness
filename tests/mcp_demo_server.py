"""A tiny MCP server used by the tests (and as a live demo).

Run on its own: `python tests/mcp_demo_server.py` speaks MCP over stdio. It
needs no API key and touches nothing on the machine, so it is safe to show.
"""
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("rootharness-demo")


@mcp.tool(description="Add two integers and return the sum.")
def add(a: int, b: int) -> int:
    return a + b


@mcp.tool(description="Return the given text in upper case.")
def shout(text: str) -> str:
    return text.upper()


if __name__ == "__main__":
    mcp.run("stdio")
