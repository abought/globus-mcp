import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from globus_compute_sdk import Client
from globus_sdk import GlobusApp, TransferClient
from mcp.server.mcpserver import MCPServer

from globus_mcp.core.auth import get_globus_app
from globus_mcp.core.filesystem import resolve_filesystem_root


@dataclass
class GlobusContext:
    app: GlobusApp
    server_session_id: str
    filesystem_root: Path | None = None
    transfer_client: TransferClient | None = None
    compute_client: Client | None = None


@asynccontextmanager
async def lifespan(server: MCPServer[GlobusContext]) -> AsyncIterator[GlobusContext]:
    try:
        app = get_globus_app()
        filesystem_root = resolve_filesystem_root()
        # NOTE: 2026 MCP is stateless, and does not provide a session ID that links to
        #  chatbot session. Server session ID is a synthetic value and cannot be directly
        #  correlated to LLM activity.
        yield GlobusContext(
            app=app,
            server_session_id=str(uuid.uuid4()),
            filesystem_root=filesystem_root,
        )
    finally:
        pass
