"""
Server configuration, set via env vars
"""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from globus_mcp.core.filesystem import resolve_filesystem_root
from globus_mcp.services.transfer.config import TransferConfig

T = TypeVar("T")


@dataclass(frozen=True)
class ServerConfig:
    filesystem_root: Path | None
    transfer: TransferConfig


def load_server_config() -> ServerConfig:
    errors: list[Exception] = []

    def _load(loader: Callable[[], T]) -> T | None:
        try:
            return loader()
        except (ValueError, ValidationError) as e:
            errors.append(e)
            return None

    filesystem_root = _load(resolve_filesystem_root)
    transfer = _load(TransferConfig)

    if errors:
        raise ExceptionGroup("Invalid server configuration", errors)

    assert transfer is not None
    return ServerConfig(filesystem_root=filesystem_root, transfer=transfer)
