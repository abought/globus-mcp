from typing import Literal

from pydantic import BaseModel, Field


class WhoAmI(BaseModel):
    identity_id: str | None = Field(
        description=(
            "The Globus identity ID of the authenticated user or client."
            " May be None if no token has been acquired yet."
        )
    )
    identity_type: Literal["user", "client"] = Field(
        description=(
            "Whether requests are made as a human user (OAuth2 UserApp)"
            " or a service account (OAuth2 ClientApp)."
        )
    )
