import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from globus_compute_sdk import Client
from globus_sdk import GlobusApp, SearchClient, TransferClient
from mcp.server.mcpserver import MCPServer

from globus_mcp.core.auth import get_globus_app
from globus_mcp.core.config import ServerConfig, load_server_config


@dataclass
class GlobusContext:
    app: GlobusApp
    server_session_id: str
    config: ServerConfig = field(default_factory=load_server_config)
    transfer_client: TransferClient | None = None
    compute_client: Client | None = None
    search_client: SearchClient | None = None


@asynccontextmanager
async def lifespan(server: MCPServer[GlobusContext]) -> AsyncIterator[GlobusContext]:
    try:
        app = get_globus_app()
        config = load_server_config()
        # NOTE: 2026 MCP is stateless, and does not provide a session ID that links to
        #  chatbot session. Server session ID is a synthetic value and cannot be directly
        #  correlated to LLM activity.
        yield GlobusContext(
            app=app,
            server_session_id=str(uuid.uuid4()),
            config=config,
        )
    finally:
        pass
