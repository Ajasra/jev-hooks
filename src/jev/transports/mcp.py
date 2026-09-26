"""Optional MCP surface backed by the same core services as lifecycle hooks."""

from __future__ import annotations

from functools import partial

from jev.registry import TOOLS
from jev.services.paths import Settings
from jev.tooling import HANDLERS


def create_server(settings: Settings):
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError("Install the 'mcp' extra to run Jev's MCP server") from exc

    server = MCPServer("jev-shared-runtime", version="0.1.0")

    for spec in TOOLS:
        handler = partial(HANDLERS[spec.handler_name], settings)
        handler.__name__ = spec.name
        handler.__doc__ = spec.description
        server.tool(name=spec.name, description=spec.description)(handler)

    return server
