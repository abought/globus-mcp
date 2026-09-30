"""Filesystem type operations (list, stat, etc)"""

from typing import Annotated

import globus_sdk
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from globus_mcp.core.audit import audited
from globus_mcp.core.context import GlobusContext
from globus_mcp.services.transfer.client import get_transfer_client
from globus_mcp.services.transfer.schemas.fs import TransferFile, TransferFileList
from globus_mcp.services.transfer.whitelist import check_source_allowed

_SERVICE = "transfer"


@audited(_SERVICE)
def globus_transfer_list_directory_contents(
    collection_id: Annotated[str, Field(description="UUID of the collection")],
    path: Annotated[str, Field(description="Path to a directory")],
    limit: Annotated[
        int, Field(le=100_000, description="Maximum number of results to return.")
    ] = 100,
    offset: Annotated[int, Field(description="Zero based offset into the result set.")] = 0,
    show_hidden: Annotated[
        bool,
        Field(description="Include files and directories whose names begin with a dot."),
    ] = True,
    *,
    ctx: Context[GlobusContext],
) -> TransferFileList:
    """List contents of a directory on a Globus Transfer collection. Note: Not recursive."""
    try:
        check_source_allowed(ctx.request_context.lifespan_context.config.transfer, collection_id)
    except ValueError as e:
        raise ToolError(str(e)) from e

    client = get_transfer_client(ctx)

    try:
        # TODO: Expose file filter param in the future when a clean LLM-facing syntax is defined
        res = client.operation_ls(
            collection_id, path=path, limit=limit, offset=offset, show_hidden=show_hidden
        )
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to list directory contents: {e}") from e

    files = []
    for f in res["DATA"]:
        file = TransferFile(
            name=f["name"],
            type=f["type"],
            link_target=f.get("link_target"),
            user=f.get("user"),
            group=f.get("group"),
            permissions=f["permissions"],
            size=f["size"],
            last_modified=f["last_modified"],
        )
        files.append(file)

    return TransferFileList(limit=limit, offset=offset, data=files)


@audited(_SERVICE)
def globus_transfer_stat_path(
    collection_id: Annotated[str, Field(description="UUID of the collection")],
    path: Annotated[str, Field(description="Path to a file or directory")],
    *,
    ctx: Context[GlobusContext],
) -> TransferFile:
    """
    Get metadata for a specific file or directory on a Globus Transfer collection.

    Useful for checking existence or confirming a path's type before running a transfer.
    Raises an error if the path does not exist.
    """
    try:
        check_source_allowed(ctx.request_context.lifespan_context.config.transfer, collection_id)
    except ValueError as e:
        raise ToolError(str(e)) from e

    client = get_transfer_client(ctx)

    try:
        f = client.operation_stat(collection_id, path=path)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to stat path: {e}") from e

    return TransferFile(
        name=f["name"],
        type=f["type"],
        link_target=f.get("link_target"),
        user=f.get("user"),
        group=f.get("group"),
        permissions=f["permissions"],
        size=f["size"],
        last_modified=f["last_modified"],
    )
