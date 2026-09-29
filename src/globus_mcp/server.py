import argparse
import sys
from collections.abc import Callable, Iterable
from importlib.metadata import version as _get_distribution_version

from mcp.server.mcpserver import MCPServer

from globus_mcp.core.audit import configure_audit_logging
from globus_mcp.core.categories import DEFAULT_CATEGORIES, ToolCategory
from globus_mcp.core.config import load_server_config
from globus_mcp.core.context import lifespan
from globus_mcp.services.auth.tools import globus_auth_whoami
from globus_mcp.services.compute.registry import register_compute
from globus_mcp.services.mount.tools import mcp_get_shared_mount_location
from globus_mcp.services.search.registry import register_search
from globus_mcp.services.transfer.registry import register_transfer

SERVER_INSTRUCTIONS = """\
The Globus research data platform enables the movement, sharing, discovery, and analysis of \
large scientific datasets. These MCP tools can be used to create and monitor Globus resources, \
and facilitate distributed multi-institution collaborations. NOTE: this MCP server only exposes \
the tools specified in server configuration. If you need a feature that is not provided, ask the \
user to enable it.
NOTE: In the past, Globus Transfer collections were sometimes referred to as "endpoints", and old \
references/ api fields may use the terms interchangeably"""

mcp = MCPServer(
    "Globus Research Data Platform",
    lifespan=lifespan,
    version=_get_distribution_version("globus-mcp"),
    instructions=SERVER_INSTRUCTIONS,
    description="Globus: Automation for the research lifecycle",
)


service_registry: dict[str, Callable[[MCPServer, Iterable[ToolCategory]], None]] = {
    "compute": register_compute,
    "search": register_search,
    "transfer": register_transfer,
}
services = list(service_registry.keys())


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Globus MCP Server")
    for service in services:
        parser.add_argument(
            f"--{service}",
            nargs="*",
            type=ToolCategory,
            default=None,
            metavar="CATEGORY",
            help=(
                f"Install {service} tools, limited to level(s) of: "
                f" ({', '.join(c.value for c in ToolCategory)})."
                f" Defaults to {[c.value for c in DEFAULT_CATEGORIES]} if no level(s) specified"
                f" Omit this flag entirely to deactivate {service} tools."
            ),
        )
    return parser.parse_args()


def resolve_categories(
    selected: list[ToolCategory] | None,
) -> tuple[ToolCategory, ...] | None:
    """Interpret a parsed `--<service>` flag's raw value.

    `None` means the flag was omitted entirely, so the service is skipped. An empty
    list means the flag was given with no categories, so it falls back to the
    default. Anything else is used as given (argparse's `type=ToolCategory` already
    restricts values to `ToolCategory` members).
    """
    if selected is None:
        return None
    if not selected:
        return DEFAULT_CATEGORIES
    return tuple(selected)


def main() -> None:
    configure_audit_logging()
    mcp.add_tool(globus_auth_whoami)

    try:
        config = load_server_config()
    except ExceptionGroup as eg:
        sys.exit("Invalid server configuration:\n" + "\n".join(str(e) for e in eg.exceptions))

    if config.filesystem_root is not None:
        mcp.add_tool(mcp_get_shared_mount_location)

    args = parse_arguments()
    for service, register in service_registry.items():
        categories = resolve_categories(getattr(args, service))
        if categories is not None:
            try:
                register(mcp, categories)
            except ValueError as e:
                sys.exit(f"Invalid configuration for --{service}: {e}")

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
