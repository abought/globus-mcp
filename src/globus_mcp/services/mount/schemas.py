from pydantic import BaseModel, Field


class SharedFilesystemLocation(BaseModel):
    path: str = Field(
        description=(
            "Absolute path to the shared filesystem root on the MCP server."
            " Files written here by MCP tools are intended to be accessible to the agent"
            " at the same path, subject to the agent's sandbox configuration."
        )
    )
