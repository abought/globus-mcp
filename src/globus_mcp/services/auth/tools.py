from typing import Literal

import globus_sdk
from mcp.server.mcpserver import Context

from globus_mcp.audit import get_globus_identity, log_tool_call, log_tool_result
from globus_mcp.context import GlobusContext
from globus_mcp.services.auth.schemas import WhoAmI

_SERVICE = "auth"


def globus_auth_whoami(ctx: Context[GlobusContext]) -> WhoAmI:
    """
    Return the Globus identity that this MCP server is using to authenticate requests.

    Use this tool to verify that the correct user or service account is active, and to
    detect credential misconfigurations before running longer operations.
    """
    log_tool_call(
        ctx,
        tool_name=globus_auth_whoami.__name__,
        service=_SERVICE,
        include_globus_identity=False,
    )

    app = ctx.request_context.lifespan_context.app
    identity_id = get_globus_identity(ctx)
    identity_type: Literal["user", "client"] = (
        "client" if isinstance(app, globus_sdk.ClientApp) else "user"
    )

    log_tool_result(
        ctx,
        tool_name=globus_auth_whoami.__name__,
        service=_SERVICE,
        result={"identity_id": identity_id, "identity_type": identity_type},
        include_globus_identity=False,
    )
    return WhoAmI(identity_id=identity_id, identity_type=identity_type)
