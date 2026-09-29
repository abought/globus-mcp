from collections.abc import Callable
from typing import Any

import globus_sdk
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from globus_mcp.core.audit import log_tool_call, log_tool_error, log_tool_result
from globus_mcp.core.categories import ToolCategory
from globus_mcp.core.context import GlobusContext
from globus_mcp.services.search.client import get_search_client
from globus_mcp.services.search.schemas import SearchIndex
from globus_mcp.services.search.whitelist import check_index_allowed

_SERVICE = "search"


def globus_search_list_indices(ctx: Context[GlobusContext]) -> list[SearchIndex]:
    """
    List Globus Search indices visible to the current user.

    Not every index will be usable by this MCP server. Check `allowed` on each entry.
    """
    log_tool_call(ctx, tool_name=globus_search_list_indices.__name__, service=_SERVICE)
    client = get_search_client(ctx)
    search_config = ctx.request_context.lifespan_context.config.search

    try:
        r = client.index_list()
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx, tool_name=globus_search_list_indices.__name__, service=_SERVICE, error=e
        )
        raise ToolError(f"Failed to list search indices: {e}") from e

    indices = []
    for idx in r.data.get("index_list", []):
        indices.append(
            SearchIndex(
                index_id=idx["id"],
                display_name=idx["display_name"],
                description=idx.get("description"),
                size=idx.get("size"),
                num_subjects=idx.get("num_subjects"),
                allowed=check_index_allowed(search_config, idx["id"], err=False),
            )
        )

    log_tool_result(
        ctx,
        tool_name=globus_search_list_indices.__name__,
        service=_SERVICE,
        result={"count": len(indices)},
    )
    return indices


SEARCH_TOOLS_BY_CATEGORY: dict[ToolCategory, list[Callable[..., Any]]] = {
    ToolCategory.READ: [globus_search_list_indices],
    ToolCategory.OPERATE: [],
    ToolCategory.ADMIN: [],
}
