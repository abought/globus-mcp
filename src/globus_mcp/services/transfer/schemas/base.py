from pydantic import BaseModel, Field


class PaginationMixin(BaseModel):
    offset: int = Field(description="Zero based offset into the result set.")
    limit: int = Field(description="Maximum number of results to return.")
