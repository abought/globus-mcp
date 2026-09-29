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
        description=(
            "Whether this server's collection allowlist policy permits using this collection"
            " as a transfer source. Always True if no source allowlist is configured."
        ),
    )
    allowed_as_destination: bool = Field(
        description=(
            "Whether this server's collection allowlist policy permits using this collection"
            " as a transfer destination. Always True if no destination allowlist is configured."
        ),
    )


class TransferCollectionList(PaginationMixin):
    has_next_page: bool = Field(
        description="Indicates whether making a query at the next offset would yield more results",
    )
    data: list[TransferCollection] = Field(
        description=(
            "Set of transfer endpoints visible to the user. Not every entry is necessarily"
            " usable as a source or destination on this server — check allowed_as_source /"
            " allowed_as_destination on each entry."
        ),
    )
