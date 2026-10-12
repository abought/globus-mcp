import globus_sdk
from globus_sdk.scopes import SearchScopes
from mcp.server.mcpserver import Context

from globus_mcp.core.context import GlobusContext


def get_search_client(ctx: Context[GlobusContext]) -> globus_sdk.SearchClient:
    globus_ctx = ctx.request_context.lifespan_context
    if globus_ctx.search_client:
        return globus_ctx.search_client

    # TODO: The beta field mapping endpoint rejects the default `search` scope. Request `all`
    #   until more granular Search scopes are available.
    globus_ctx.app.add_scope_requirements(
        {globus_sdk.SearchClient.resource_server: [SearchScopes.all]}
    )
    client = globus_sdk.SearchClient(app=globus_ctx.app)
    globus_ctx.search_client = client
    return client
