from pydantic import BaseModel, Field


class SearchIndex(BaseModel):
    index_id: str = Field(description="ID of the search index")
    display_name: str = Field(description="Display name of the index")
    description: str | None = Field(default=None, description="Description of the index")
    size: int | None = Field(default=None, description="Size of the index in bytes")
    num_subjects: int | None = Field(default=None, description="Number of subjects in the index")
    allowed: bool = Field(description="Whether this MCP server is allowed to query this index.")


class SearchIndexFieldMapping(BaseModel):
    index_id: str = Field(description="ID of the search index")
    mappings: dict[str, str] = Field(
        description=(
            "Elasticsearch-style field mappings: dotted field path"
            " to field type, eg `text`, `date`, `long`."
        )
    )
