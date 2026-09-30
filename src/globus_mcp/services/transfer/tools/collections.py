"""
Find globus collections usable by the user
"""

from typing import Annotated, Literal

import globus_sdk
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from globus_mcp.core.audit import audited
from globus_mcp.core.context import GlobusContext
from globus_mcp.services.transfer.client import get_transfer_client
from globus_mcp.services.transfer.config import TransferConfig
from globus_mcp.services.transfer.schemas.collections import (
    TransferCollection,
    TransferCollectionList,
)
from globus_mcp.services.transfer.whitelist import check_destination_allowed, check_source_allowed

_SERVICE = "transfer"


def _format_search_response(
    res: globus_sdk.IterableTransferResponse, transfer_config: TransferConfig
) -> TransferCollectionList:
    endpoints = []
    for e in res["DATA"]:
        endpoint = TransferCollection(
            endpoint_id=e["id"],
            display_name=e["display_name"],
            owner_id=e["owner_id"],
            owner_string=e["owner_string"],
            type=e["entity_type"],
            description=e.get("description"),
            allowed_as_source=check_source_allowed(transfer_config, e["id"], err=False),
            allowed_as_destination=check_destination_allowed(transfer_config, e["id"], err=False),
        )
        endpoints.append(endpoint)
    return TransferCollectionList(
        limit=res["limit"],
        offset=res["offset"],
        has_next_page=res["has_next_page"],
        data=endpoints,
    )


@audited(_SERVICE)
def globus_transfer_list_collections(
    filter_scope: Annotated[
        Literal[
            "my-endpoints",
            "administered-by-me",
            "shared-with-me",
            "shared-by-me",
            "recently-used",
            "in-use",
        ],
        Field(
            description=(
                "String indicating which scope/class of collections to list."
                " Options:"
                " my-endpoints (owned by the user),"
                " administered-by-me (user has admin role, superset of my-endpoints),"
                " shared-with-me (shared with user),"
                " shared-by-me (guest collections where user is admin or access manager),"
                " recently-used (default; recently used by user),"
                " in-use (with active tasks owned by user),"
            ),
        ),
    ] = "my-endpoints",
    limit: Annotated[int, Field(le=100, description="Maximum number of results to return.")] = 100,
    offset: Annotated[int, Field(description="Zero based offset into the result set.")] = 0,
    *,
    ctx: Context[GlobusContext],
) -> TransferCollectionList:
    """
    List Globus Transfer collections (storage locations) that the user has access to.

    Not every collection will be usable by this MCP server.
        Check `allowed_as_source` / `allowed_as_destination`
    """
    client = get_transfer_client(ctx)

    try:
        res = client.endpoint_search(
            filter_scope=filter_scope,
            limit=limit,
            offset=offset,
        )
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to get search results: {e}") from e

    return _format_search_response(res, ctx.request_context.lifespan_context.config.transfer)


@audited(_SERVICE)
def globus_transfer_search_collections(
    filter_fulltext: Annotated[
        str,
        Field(min_length=1, description="String to match collection fields against."),
    ],
    limit: Annotated[int, Field(le=100, description="Maximum number of results to return.")] = 100,
    offset: Annotated[int, Field(description="Zero based offset into the result set.")] = 0,
    *,
    ctx: Context[GlobusContext],
) -> TransferCollectionList:
    """
    Find any (user-visible) Globus collection where any field matches the specified filter string.

    Not every collection will be usable by this MCP server.
        Check `allowed_as_source` / `allowed_as_destination`
    """
    client = get_transfer_client(ctx)

    try:
        res = client.endpoint_search(
            # TODO: Add better filter scopes etc
            filter_scope="all",
            filter_fulltext=filter_fulltext,
            limit=limit,
            offset=offset,
        )
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to get search results: {e}") from e

    return _format_search_response(res, ctx.request_context.lifespan_context.config.transfer)
