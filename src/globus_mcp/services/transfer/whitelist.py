"""
Enforce "collection whitelist" behaviors.
"""

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
