from collections.abc import Iterable

from mcp.server.mcpserver import MCPServer

from globus_mcp.categories import ToolCategory
from globus_mcp.services.compute.tools import COMPUTE_TOOLS_BY_CATEGORY
from globus_mcp.services.registry import register_tools_by_category


def register_compute(mcp: MCPServer, categories: Iterable[ToolCategory]) -> None:
    register_tools_by_category(mcp, COMPUTE_TOOLS_BY_CATEGORY, categories)
