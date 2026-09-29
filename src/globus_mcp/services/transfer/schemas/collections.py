from pydantic import BaseModel, Field

from globus_mcp.services.transfer.schemas.base import PaginationMixin


class TransferCollection(BaseModel):
    endpoint_id: str = Field(description="ID of the endpoint")
    display_name: str = Field(description="Friendly name for the endpoint")
    owner_id: str = Field(description="ID of the endpoint owner")
    owner_string: str = Field(description="Identity name of the endpoint owner")
    type: str = Field(description="The type of endpoint")
    description: str | None = Field(default=None, description="A description of the endpoint")
    allowed_as_source: bool = Field(
        description="Whether this MCP server allows using this collection as a source.",
    )
    allowed_as_destination: bool = Field(
        description="Whether this MCP server allows using this collection as a destination."

    )


class TransferCollectionList(PaginationMixin):
    has_next_page: bool = Field(
        description="Indicates whether making a query at the next offset would yield more results",
    )
    data: list[TransferCollection] = Field(
        description=(
            "Set of transfer endpoints visible to the user. See `allowed_as_source` / "
            " `allowed_as_destination` for whether this MCP server can use this collection."
        ),
    )
