from pydantic import BaseModel, Field

from globus_mcp.services.transfer.schemas.base import PaginationMixin


class TransferEndpoint(BaseModel):
    endpoint_id: str = Field(description="ID of the endpoint")
    display_name: str = Field(description="Friendly name for the endpoint")
    owner_id: str = Field(description="ID of the endpoint owner")
    owner_string: str = Field(description="Identity name of the endpoint owner")
    type: str = Field(description="The type of endpoint")
    description: str | None = Field(default=None, description="A description of the endpoint")


class TransferCollectionList(PaginationMixin):
    has_next_page: bool = Field(
        description="Indicates whether making a query at the next offset would yield more results",
    )
    data: list[TransferEndpoint] = Field(description="Set of transfer endpoints")
