from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from globus_mcp.core.fields import UUIDList


class SearchConfig(BaseSettings):
    model_config = SettingsConfigDict(frozen=True, populate_by_name=True)

    whitelist: UUIDList = Field(default=None, validation_alias="GLOBUS_SEARCH_ALLOWED_INDICES")
