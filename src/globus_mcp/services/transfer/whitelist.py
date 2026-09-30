"""
Enforce "collection whitelist" behaviors.
"""

import functools
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from globus_mcp.services.transfer.config import TransferConfig


def check_source_allowed(config: TransferConfig, collection_id: str, *, err: bool = True) -> bool:
    """
    Check whether collection_id is permitted as a transfer source.
    """
    allowed = config.source_whitelist is None or collection_id in config.source_whitelist
    if not allowed and err:
        raise ValueError(
            f"Collection {collection_id!r} is not permitted as a source collection."
            " This server restricts source collections to an administrator-configured"
            " allowlist (GLOBUS_TRANSFER_ALLOWED_SOURCE_COLLECTIONS)."
        )
    return allowed


def check_destination_allowed(
    config: TransferConfig, collection_id: str, *, err: bool = True
) -> bool:
    """
    Check whether collection_id is permitted as a transfer destination.

    If err is True (default), raise ValueError when not permitted. If err is False, never
    raise — just return the bool.
    """
    allowed = config.destination_whitelist is None or collection_id in config.destination_whitelist
    if not allowed and err:
        raise ValueError(
            f"Collection {collection_id!r} is not permitted as a destination collection."
            " This server restricts destination collections to an administrator-configured"
            " allowlist (GLOBUS_TRANSFER_ALLOWED_DESTINATION_COLLECTIONS)."
        )
    return allowed


def transfer_whitelist(
    *, source: str | None = None, destination: str | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Reject a tool call if a collection is not permitted by the transfer whitelists.

    `source` and `destination` are the names of the tool parameters holding the collection ID to
    check in that role (at least one is required). A denial becomes a `ToolError`, so the LLM can
    see why.
    """
    if source is None and destination is None:
        raise TypeError("transfer_whitelist needs a source and/or destination parameter name")

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            config = kwargs["ctx"].request_context.lifespan_context.config.transfer
            try:
                if source is not None:
                    check_source_allowed(config, kwargs[source])
                if destination is not None:
                    check_destination_allowed(config, kwargs[destination])
            except ValueError as e:
                raise ToolError(str(e)) from e
            return fn(*args, **kwargs)

        return wrapper

    return decorator
