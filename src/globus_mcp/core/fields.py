"""
Reusable fields for server-level config.
"""

import uuid
from typing import Annotated

from pydantic import BeforeValidator


def _parse_uuid_list(v: str | tuple[str, ...] | None) -> tuple[str, ...] | None:
    """
    Parse a comma-separated string of UUIDs into a tuple of strings.

    Raises ValueError if the environment variable is malformed (no valid UUIDs)
    """
    if not isinstance(v, str):
        return v

    raw = v.strip()
    if not raw:
        return None

    items = [item.strip() for item in raw.split(",") if item.strip()]
    if not items:
        raise ValueError(f"contains no usable entries: {raw!r}")

    for item in items:
        try:
            uuid.UUID(item)
        except ValueError as e:
            raise ValueError(f"contains an entry that is not a valid UUID: {item!r}") from e
    return tuple(items)


# FIELD type: Parse an envvar into a comma-separated list of UUIDs
UUIDList = Annotated[tuple[str, ...] | None, BeforeValidator(_parse_uuid_list)]
