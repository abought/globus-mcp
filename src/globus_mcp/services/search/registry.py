from collections.abc import Iterable

from mcp.server.mcpserver import MCPServer

from globus_mcp.core.categories import ToolCategory
from globus_mcp.services.registry import register_tools_by_category
from globus_mcp.services.search.tools import SEARCH_TOOLS_BY_CATEGORY


def register_search(mcp: MCPServer, categories: Iterable[ToolCategory]) -> None:
    register_tools_by_category(mcp, SEARCH_TOOLS_BY_CATEGORY, categories)
