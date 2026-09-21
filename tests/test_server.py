from unittest.mock import Mock, patch

import pytest

from globus_mcp.categories import DEFAULT_CATEGORIES, ToolCategory
from globus_mcp.server import main, mcp, services
from tests.utils import random_string


@pytest.fixture
def mock_service_registry():
    with patch.dict(
        "globus_mcp.server.service_registry", {s: Mock() for s in services}
    ) as service_registry:
        yield service_registry


@patch.object(mcp, "run")
def test_run_server_default(mock_mcp_run: Mock, mock_service_registry: dict[str, Mock]):
    """With no flags at all, no service should be registered."""
    with patch("sys.argv", ["globus-mcp"]):
        main()
        for service in services:
            mock_service_registry[service].assert_not_called()
        mock_mcp_run.assert_called_once_with(transport="stdio")


@patch.object(mcp, "run")
@pytest.mark.parametrize("service", services)
def test_run_server_flag_with_no_categories_defaults(
    mock_mcp_run: Mock, service: str, mock_service_registry: dict[str, Mock]
):
    """A `--<service>` flag given with no categories falls back to the default."""
    with patch("sys.argv", ["globus-mcp", f"--{service}"]):
        main()
        mock_service_registry[service].assert_called_once_with(mcp, DEFAULT_CATEGORIES)
        mock_mcp_run.assert_called_once_with(transport="stdio")


@patch.object(mcp, "run")
@pytest.mark.parametrize("service", services)
def test_run_server_flag_with_explicit_categories(
    mock_mcp_run: Mock, service: str, mock_service_registry: dict[str, Mock]
):
    with patch("sys.argv", ["globus-mcp", f"--{service}", "read", "admin"]):
        main()
        mock_service_registry[service].assert_called_once_with(mcp, ("read", "admin"))
        mock_mcp_run.assert_called_once_with(transport="stdio")


@patch.object(mcp, "run")
def test_run_server_flag_omitted_registers_nothing_for_that_service(
    mock_mcp_run: Mock, mock_service_registry: dict[str, Mock]
):
    with patch("sys.argv", ["globus-mcp", "--compute", "read"]):
        main()
        mock_service_registry["compute"].assert_called_once_with(mcp, ("read",))
        for service in services:
            if service != "compute":
                mock_service_registry[service].assert_not_called()
        mock_mcp_run.assert_called_once_with(transport="stdio")


@patch.object(mcp, "run")
@pytest.mark.parametrize("service", services)
def test_run_server_with_all_categories(
    mock_mcp_run: Mock, service: str, mock_service_registry: dict[str, Mock]
):
    with patch("sys.argv", ["globus-mcp", f"--{service}", *ToolCategory]):
        main()
        mock_service_registry[service].assert_called_once_with(mcp, tuple(ToolCategory))
        mock_mcp_run.assert_called_once_with(transport="stdio")


@patch.object(mcp, "run")
@pytest.mark.parametrize("service", services)
def test_run_server_with_invalid_category(mock_mcp_run: Mock, service: str):
    args = ["globus-mcp", f"--{service}", random_string()]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2  # argparse error exit code
        mock_mcp_run.assert_not_called()
