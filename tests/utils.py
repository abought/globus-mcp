import random
import string
from unittest.mock import Mock

from globus_mcp.core.config import ServerConfig
from globus_mcp.services.transfer.config import TransferConfig


def random_string(length: int = 10):
    letters = string.ascii_lowercase
    return "".join(random.choice(letters) for _ in range(length))


def set_restricted_config(
    ctx: Mock,
    *,
    source: tuple[str, ...] | None = None,
    destination: tuple[str, ...] | None = None,
) -> None:
    """Replace a mock_ctx's ServerConfig with one restricting the given whitelist(s)."""
    ctx.request_context.lifespan_context.config = ServerConfig(
        filesystem_root=None,
        transfer=TransferConfig(source_whitelist=source, destination_whitelist=destination),
    )
