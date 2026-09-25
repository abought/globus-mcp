from collections.abc import Iterable

from mcp.server.mcpserver import MCPServer

from globus_mcp.core.categories import ToolCategory

from globus_mcp.services.registry import register_tools_by_category
from globus_mcp.services.transfer.tools import (
    TRANSFER_FILE_TOOLS_BY_CATEGORY,
    TRANSFER_TOOLS_BY_CATEGORY,
)


def register_transfer(mcp: MCPServer, categories: Iterable[ToolCategory]) -> None:
    register_tools_by_category(mcp, TRANSFER_TOOLS_BY_CATEGORY, categories)
