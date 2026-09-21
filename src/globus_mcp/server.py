import argparse
from collections.abc import Callable, Iterable

from mcp.server.mcpserver import MCPServer

from globus_mcp.categories import DEFAULT_CATEGORIES, ToolCategory
from globus_mcp.context import lifespan
from globus_mcp.services.compute.registry import register_compute
from globus_mcp.services.transfer.registry import register_transfer

mcp = MCPServer("Globus MCP Server", lifespan=lifespan)


service_registry: dict[str, Callable[[MCPServer, Iterable[ToolCategory]], None]] = {
    "compute": register_compute,
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
    args = parse_arguments()
    for service, register in service_registry.items():
        categories = resolve_categories(getattr(args, service))
        if categories is not None:
            register(mcp, categories)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
