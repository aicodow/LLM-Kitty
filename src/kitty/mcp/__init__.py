"""MCP (Model Context Protocol) server package for Kitty framework.

Exposes evaluation and red-teaming capabilities as MCP tools over
stdio transport.
"""

from .server import MCPServer

__all__ = [
    "MCPServer",
]
