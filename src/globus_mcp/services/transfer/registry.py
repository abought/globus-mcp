from collections.abc import Iterable

from mcp.server.mcpserver import MCPServer

from globus_mcp.core.categories import ToolCategory
from globus_mcp.core.filesystem import resolve_filesystem_root
from globus_mcp.services.registry import register_tools_by_category
from globus_mcp.services.transfer.tools import (
    TRANSFER_FILE_TOOLS_BY_CATEGORY,
    TRANSFER_TOOLS_BY_CATEGORY,
)


def register_transfer(mcp: MCPServer, categories: Iterable[ToolCategory]) -> None:
    register_tools_by_category(mcp, TRANSFER_TOOLS_BY_CATEGORY, categories)

    # resolve_filesystem_root() validates fully (existence, overlap checks) and raises
    # ValueError on misconfiguration, which fails the server at startup — intentional.
    if resolve_filesystem_root() is not None:
        register_tools_by_category(mcp, TRANSFER_FILE_TOOLS_BY_CATEGORY, categories)
