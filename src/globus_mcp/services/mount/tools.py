from mcp.server.mcpserver import Context

from globus_mcp.core.audit import log_tool_call, log_tool_result
from globus_mcp.core.context import GlobusContext
from globus_mcp.services.mount.schemas import SharedFilesystemLocation

_SERVICE = "mount"


def mcp_get_shared_mount_location(
    *,
    ctx: Context[GlobusContext],
) -> SharedFilesystemLocation:
    """
    This MCP server is able to share a directory with the coding agent,
      for data too big to be read or written directly from model context.

    For example, the coding agent could generate a file from a big dataset using
      one-off scripts, and then provide certain mcp tools the path to the result file.

    When this server is configured, it is up to the user to set a path accessible to both the MCP
     server and the coding agent. After retrieving this path, the client should make sure that it
     is readable before performing any filesystem operations.  Warn the user if config changes
     are needed.
    """
    filesystem_root = ctx.request_context.lifespan_context.filesystem_root
    assert filesystem_root is not None  # guaranteed by conditional registration
    log_tool_call(ctx, tool_name=mcp_get_shared_mount_location.__name__, service=_SERVICE)
    log_tool_result(
        ctx,
        tool_name=mcp_get_shared_mount_location.__name__,
        service=_SERVICE,
        result={"path": str(filesystem_root)},
    )
    return SharedFilesystemLocation(path=str(filesystem_root))
