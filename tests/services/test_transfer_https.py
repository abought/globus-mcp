import uuid
from unittest.mock import Mock, patch

import pytest
from globus_sdk import TransferClient
from mcp.server.mcpserver.exceptions import ToolError

from globus_mcp.services.transfer.tools.https import (
    globus_transfer_direct_read_content,
    globus_transfer_direct_upload_content_via_https,
    globus_transfer_download_file_via_https,
    globus_transfer_upload_file_via_https,
)
from tests.utils import random_string, set_restricted_config


@pytest.fixture
def mock_client():
    mc = Mock(spec=TransferClient)
    with patch("globus_mcp.services.transfer.tools.https.get_transfer_client", return_value=mc):
        yield mc


@pytest.fixture
def mock_https_auth_header():
    with patch("globus_mcp.services.transfer.tools.https._get_https_auth_header") as mocked:
        yield mocked


def test_direct_upload_content_disallowed_destination(
    mock_ctx: Mock, mock_client: Mock, mock_https_auth_header: Mock
):
    set_restricted_config(mock_ctx, destination=(str(uuid.uuid4()),))
    with pytest.raises(ToolError, match="not permitted as a destination collection"):
        globus_transfer_direct_upload_content_via_https(
            collection_id=str(uuid.uuid4()),
            dest_path="/file.txt",
            content=random_string(),
            ctx=mock_ctx,
        )
    mock_client.operation_stat.assert_not_called()
    mock_https_auth_header.assert_not_called()


def test_direct_read_content_disallowed_source(mock_ctx: Mock, mock_https_auth_header: Mock):
    set_restricted_config(mock_ctx, source=(str(uuid.uuid4()),))
    with pytest.raises(ToolError, match="not permitted as a source collection"):
        globus_transfer_direct_read_content(
            collection_id=str(uuid.uuid4()),
            source_path="/file.txt",
            ctx=mock_ctx,
        )
    mock_https_auth_header.assert_not_called()


def test_upload_file_via_https_disallowed_destination(
    mock_ctx: Mock, mock_client: Mock, mock_https_auth_header: Mock
):
    set_restricted_config(mock_ctx, destination=(str(uuid.uuid4()),))
    with pytest.raises(ToolError, match="not permitted as a destination collection"):
        globus_transfer_upload_file_via_https(
            collection_id=str(uuid.uuid4()),
            dest_path="/file.txt",
            local_path="file.txt",
            ctx=mock_ctx,
        )
    mock_client.operation_stat.assert_not_called()
    mock_https_auth_header.assert_not_called()


def test_download_file_via_https_disallowed_source(mock_ctx: Mock, mock_https_auth_header: Mock):
    set_restricted_config(mock_ctx, source=(str(uuid.uuid4()),))
    with pytest.raises(ToolError, match="not permitted as a source collection"):
        globus_transfer_download_file_via_https(
            collection_id=str(uuid.uuid4()),
            source_path="/file.txt",
            ctx=mock_ctx,
        )
    mock_https_auth_header.assert_not_called()
