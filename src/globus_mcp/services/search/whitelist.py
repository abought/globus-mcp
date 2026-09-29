"""
Enforce "index whitelist" behaviors.
"""

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
