from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from globus_mcp.core.fields import UUIDList


class TransferConfig(BaseSettings):
    model_config = SettingsConfigDict(frozen=True, populate_by_name=True)

    source_whitelist: UUIDList = Field(
        default=None, validation_alias="GLOBUS_TRANSFER_ALLOWED_SOURCE_COLLECTIONS"
    )
    destination_whitelist: UUIDList = Field(
        default=None, validation_alias="GLOBUS_TRANSFER_ALLOWED_DESTINATION_COLLECTIONS"
    )
