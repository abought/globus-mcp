from collections.abc import Callable, Iterable, Mapping
from typing import Any

from mcp.server.mcpserver import MCPServer

from globus_mcp.categories import ToolCategory


def register_tools_by_category(
    mcp: MCPServer,
    tools_by_category: Mapping[ToolCategory, list[Callable[..., Any]]],
    categories: Iterable[ToolCategory],
) -> None:
    """Shared helper: register only the tools needed for a given service and permissions level"""
    for category in categories:
        for tool in tools_by_category[category]:
            mcp.add_tool(tool)
