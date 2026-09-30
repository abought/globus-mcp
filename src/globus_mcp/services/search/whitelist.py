"""
Enforce "index whitelist" behaviors.
"""

import functools
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from globus_mcp.services.search.config import SearchConfig


def check_index_allowed(config: SearchConfig, index_id: str, *, err: bool = True) -> bool:
    """
    Check whether index_id is permitted for use by search tools.

    If err is True (default), raise ValueError when not permitted. If err is False, never
    raise — just return the bool.
    """
    allowed = config.whitelist is None or index_id in config.whitelist
    if not allowed and err:
        raise ValueError(
            f"Index {index_id!r} is not permitted."
            " This server restricts search indices to an administrator-configured"
            " allowlist (GLOBUS_SEARCH_ALLOWED_INDICES)."
        )
    return allowed


def search_whitelist(index: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Reject a tool call if an index is not permitted by the search whitelist.

    `index` is the name of the tool parameter holding the index ID. A denial becomes a
    `ToolError`, so the LLM can see why.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            config = kwargs["ctx"].request_context.lifespan_context.config.search
            try:
                check_index_allowed(config, kwargs[index])
            except ValueError as e:
                raise ToolError(str(e)) from e
            return fn(*args, **kwargs)

        return wrapper

    return decorator
