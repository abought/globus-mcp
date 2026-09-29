import random
import uuid
from http import HTTPStatus
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from globus_sdk import GlobusAPIError, IterableTransferResponse, TransferClient, TransferData
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from globus_mcp.core.categories import ToolCategory
from globus_mcp.core.context import GlobusContext
from globus_mcp.server import service_registry
from globus_mcp.services.transfer.client import get_transfer_client
from globus_mcp.services.transfer.config import TransferConfig
from globus_mcp.services.transfer.registry import register_transfer
from globus_mcp.services.transfer.schemas import TransferItem
from globus_mcp.services.transfer.tools import (
    TRANSFER_TOOLS_BY_CATEGORY,
    globus_transfer_get_task_events,
    globus_transfer_get_task_status,
    globus_transfer_list_collections,
    globus_transfer_list_directory_contents,
    globus_transfer_search_collections,
    globus_transfer_stat_path,
    globus_transfer_submit_file_transfer_task,
)
from globus_mcp.services.transfer.tools.collections import _format_search_response
from globus_mcp.services.transfer.tools.tasks import _handle_gare
from tests.utils import random_string, set_restricted_config


@pytest.fixture
def mock_client():
    # get_transfer_client is imported directly into each tools submodule, so it must be
    # patched at each of those three call sites (not on the tools package itself).
    mc = Mock(spec=TransferClient)
    target = "globus_mcp.services.transfer.tools.{}.get_transfer_client"
    with (
        patch(target.format("collections"), return_value=mc),
        patch(target.format("fs"), return_value=mc),
        patch(target.format("tasks"), return_value=mc),
    ):
        yield mc


@pytest.fixture
def mock_handle_gare():
    with patch("globus_mcp.services.transfer.tools.tasks._handle_gare") as _mock_handle_gare:
        yield _mock_handle_gare


@pytest.fixture
def mock_format_search_res():
    with patch(
        "globus_mcp.services.transfer.tools.collections._format_search_response"
    ) as _format_search_res:
        yield _format_search_res


def test_transfer_in_service_registry():
    assert "transfer" in service_registry
    assert service_registry["transfer"] is register_transfer


def test_register_transfer():
    mcp = Mock(spec=MCPServer)
    register_transfer(mcp, [ToolCategory.READ, ToolCategory.OPERATE, ToolCategory.ADMIN])
    registered = [c[0][0] for c in mcp.add_tool.call_args_list]
    for tools in TRANSFER_TOOLS_BY_CATEGORY.values():
        for tool in tools:
            assert tool in registered


def test_register_transfer_by_category():
    mcp = Mock(spec=MCPServer)
    register_transfer(mcp, [ToolCategory.OPERATE])
    registered = [c[0][0] for c in mcp.add_tool.call_args_list]
    assert registered == TRANSFER_TOOLS_BY_CATEGORY[ToolCategory.OPERATE]


def test_get_transfer_client(mock_ctx: Mock):
    globus_ctx: GlobusContext = mock_ctx.request_context.lifespan_context
    globus_ctx.app.app_name = random_string()
    assert globus_ctx.transfer_client is None, "Ensure setup"

    client = get_transfer_client(mock_ctx)
    assert globus_ctx.transfer_client is client
    assert isinstance(client, TransferClient)
    assert client.app_name == globus_ctx.app.app_name

    client_2 = get_transfer_client(mock_ctx)
    assert client_2 is client, "Client should be cached"


def test_handle_gare_happy_path(mock_client: Mock):
    res_data = random_string()
    mock_client.some_method = Mock()
    mock_client.some_method.return_value = res_data
    mock_client.some_method.__self__ = mock_client

    args = (random_string(), random_string())
    kwargs = {random_string(): random_string()}
    res = _handle_gare(mock_client.some_method, *args, **kwargs)

    assert res == res_data
    mock_client.some_method.assert_called_once_with(*args, **kwargs)


def test_handle_gare_consent_required(mock_client: Mock):
    error = GlobusAPIError(r=MagicMock())
    error.http_status = HTTPStatus.FORBIDDEN
    error.code = "ConsentRequired"
    required_scopes = [random_string(), random_string()]
    error.info.consent_required.required_scopes = required_scopes

    res_data = random_string()
    mock_client.some_method = Mock()
    mock_client.some_method.side_effect = [error, res_data]
    mock_client.some_method.__self__ = mock_client

    args = (random_string(), random_string())
    kwargs = {random_string(): random_string()}
    res = _handle_gare(mock_client.some_method, *args, **kwargs)

    assert res == res_data
    assert mock_client.some_method.call_count == 2
    mock_client.some_method.assert_called_with(*args, **kwargs)
    added_scopes = [s[0][0] for s in mock_client.add_app_scope.call_args_list]
    for scope in required_scopes:
        assert scope in added_scopes


def test_handle_gare_unexpected_error(mock_client: Mock):
    error = GlobusAPIError(r=MagicMock())
    error.http_status = HTTPStatus.INTERNAL_SERVER_ERROR

    mock_client.some_method = Mock()
    mock_client.some_method.side_effect = error
    mock_client.some_method.__self__ = mock_client

    with pytest.raises(GlobusAPIError):
        _handle_gare(mock_client.some_method)


def _mock_search_response(res_data: dict[str, Any]) -> Mock:
    mock_res = Mock(spec=IterableTransferResponse)
    mock_res.__getitem__ = Mock(side_effect=lambda k: res_data[k])
    mock_res.get = Mock(side_effect=lambda k, d=None: res_data.get(k, d))
    mock_res.__iter__ = Mock(return_value=iter(res_data["DATA"]))
    return mock_res


def test_format_search_response():
    config = TransferConfig(source_whitelist=None, destination_whitelist=None)

    res_data: dict[str, Any] = {
        "limit": random.randint(1, 1000),
        "offset": random.randint(0, 1000),
        "has_next_page": False,
        "DATA": [],
    }
    for _ in range(random.randint(1, 10)):
        res_data["DATA"].append(
            {
                "id": str(uuid.uuid4()),
                "display_name": random_string(),
                "owner_id": str(uuid.uuid4()),
                "owner_string": random_string(),
                "entity_type": random_string(),
                "description": random_string(),
            }
        )

    res = _format_search_response(_mock_search_response(res_data), config)

    assert res.limit == res_data["limit"]
    assert res.offset == res_data["offset"]
    assert res.has_next_page == res_data["has_next_page"]
    assert len(res.data) == len(res_data["DATA"])
    for idx, ep in enumerate(res.data):
        ep_data = res_data["DATA"][idx]
        assert ep.endpoint_id == ep_data["id"]
        assert ep.display_name == ep_data["display_name"]
        assert ep.owner_id == ep_data["owner_id"]
        assert ep.owner_string == ep_data["owner_string"]
        assert ep.type == ep_data["entity_type"]
        assert ep.description == ep_data["description"]
        # No allowlist configured: every collection is usable in every role.
        assert ep.allowed_as_source is True
        assert ep.allowed_as_destination is True


def test_format_search_response_marks_usability_without_filtering():
    source_only = str(uuid.uuid4())  # allowed as source only
    dest_only = str(uuid.uuid4())  # allowed as destination only
    both = str(uuid.uuid4())  # allowed as both
    neither = str(uuid.uuid4())  # allowed as neither -> still returned, flagged False/False

    config = TransferConfig(
        source_whitelist=(source_only, both),
        destination_whitelist=(dest_only, both),
    )

    res_data: dict[str, Any] = {
        "limit": 100,
        "offset": 0,
        "has_next_page": False,
        "DATA": [
            {
                "id": cid,
                "display_name": random_string(),
                "owner_id": str(uuid.uuid4()),
                "owner_string": random_string(),
                "entity_type": random_string(),
                "description": None,
            }
            for cid in (source_only, dest_only, both, neither)
        ],
    }

    res = _format_search_response(_mock_search_response(res_data), config)

    # Nothing is filtered out — every upstream result is still returned, and pagination
    # fields (limit/offset/has_next_page) continue to describe the unmodified upstream page.
    returned_ids = {ep.endpoint_id: ep for ep in res.data}
    assert set(returned_ids) == {source_only, dest_only, both, neither}
    assert res.limit == res_data["limit"]
    assert res.offset == res_data["offset"]
    assert res.has_next_page == res_data["has_next_page"]

    assert returned_ids[source_only].allowed_as_source is True
    assert returned_ids[source_only].allowed_as_destination is False

    assert returned_ids[dest_only].allowed_as_source is False
    assert returned_ids[dest_only].allowed_as_destination is True

    assert returned_ids[both].allowed_as_source is True
    assert returned_ids[both].allowed_as_destination is True

    assert returned_ids[neither].allowed_as_source is False
    assert returned_ids[neither].allowed_as_destination is False


def test_globus_transfer_list_collections(
    mock_ctx: Mock, mock_client: Mock, mock_format_search_res: Mock
):
    limit = random.randint(1, 100)
    offset = random.randint(0, 100)

    search_res = Mock()
    formatted_res = Mock()
    mock_client.endpoint_search.return_value = search_res
    mock_format_search_res.return_value = formatted_res

    filter_scope = random_string()
    res = globus_transfer_list_collections(
        filter_scope=filter_scope,
        limit=limit,
        offset=offset,
        ctx=mock_ctx,
    )

    mock_client.endpoint_search.assert_called_once_with(
        filter_scope=filter_scope,
        limit=limit,
        offset=offset,
    )
    mock_format_search_res.assert_called_once_with(
        search_res, mock_ctx.request_context.lifespan_context.config.transfer
    )
    assert res == formatted_res


def test_globus_transfer_list_collections_api_error(mock_ctx: Mock, mock_client: Mock):
    mock_client.endpoint_search.side_effect = GlobusAPIError(r=MagicMock())
    with pytest.raises(ToolError, match="Failed to get search results"):
        globus_transfer_list_collections(
            filter_scope=random_string(),
            limit=100,
            offset=0,
            ctx=mock_ctx,
        )


def test_globus_transfer_search_collections(
    mock_ctx: Mock, mock_client: Mock, mock_format_search_res: Mock
):
    limit = random.randint(1, 100)
    offset = random.randint(0, 100)

    search_res = Mock()
    formatted_res = Mock()
    mock_client.endpoint_search.return_value = search_res
    mock_format_search_res.return_value = formatted_res

    filter_fulltext = random_string()
    res = globus_transfer_search_collections(
        filter_fulltext=filter_fulltext,
        limit=limit,
        offset=offset,
        ctx=mock_ctx,
    )

    mock_client.endpoint_search.assert_called_once_with(
        filter_scope="all",
        filter_fulltext=filter_fulltext,
        limit=limit,
        offset=offset,
    )
    mock_format_search_res.assert_called_once_with(
        search_res, mock_ctx.request_context.lifespan_context.config.transfer
    )
    assert res == formatted_res


def test_globus_transfer_search_collections_api_error(mock_ctx: Mock, mock_client: Mock):
    mock_client.endpoint_search.side_effect = GlobusAPIError(r=MagicMock())
    with pytest.raises(ToolError, match="Failed to get search results"):
        globus_transfer_search_collections(
            filter_fulltext=random_string(),
            limit=100,
            offset=0,
            ctx=mock_ctx,
        )


def test_globus_transfer_submit_file_transfer_task(
    mock_ctx: Mock, mock_client: Mock, mock_handle_gare: Mock
):
    source_collection_id = str(uuid.uuid4())
    destination_collection_id = str(uuid.uuid4())
    source_path = random_string()
    destination_path = random_string()
    label = random_string()
    task_id = str(uuid.uuid4())

    expected_data = TransferData(
        source_endpoint=source_collection_id,
        destination_endpoint=destination_collection_id,
        label=label,
        sync_level="checksum",  # tool default when not explicitly passed
        encrypt_data=True,
        fail_on_quota_errors=True,
        delete_destination_extra=False,
        notify_on_succeeded=True,
        notify_on_failed=True,
        notify_on_inactive=True,
        verify_checksum=False,
        skip_source_errors=False,
    )
    expected_data.add_item(source_path=source_path, destination_path=destination_path)

    mock_handle_gare.return_value = Mock(data={"task_id": task_id})

    res = globus_transfer_submit_file_transfer_task(
        source_collection_id=source_collection_id,
        destination_collection_id=destination_collection_id,
        items=[TransferItem(source_path=source_path, destination_path=destination_path)],
        label=label,
        ctx=mock_ctx,
    )

    mock_handle_gare.assert_called_once_with(mock_client.submit_transfer, expected_data)
    assert res.task_id == task_id


def test_globus_transfer_submit_file_transfer_task_with_options(
    mock_ctx: Mock, mock_client: Mock, mock_handle_gare: Mock
):
    source_collection_id = str(uuid.uuid4())
    destination_collection_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    expected_data = TransferData(
        source_endpoint=source_collection_id,
        destination_endpoint=destination_collection_id,
        label="Globus MCP Transfer",
        sync_level="checksum",
        encrypt_data=True,
        fail_on_quota_errors=True,
        delete_destination_extra=False,
        notify_on_succeeded=True,
        notify_on_failed=True,
        notify_on_inactive=True,
        verify_checksum=True,
        skip_source_errors=True,
    )
    dir_path = random_string()
    expected_data.add_item(source_path=dir_path, destination_path=dir_path, recursive=True)

    mock_handle_gare.return_value = Mock(data={"task_id": task_id})

    res = globus_transfer_submit_file_transfer_task(
        source_collection_id=source_collection_id,
        destination_collection_id=destination_collection_id,
        items=[TransferItem(source_path=dir_path, destination_path=dir_path, recursive=True)],
        sync_level="checksum",
        verify_checksum=True,
        skip_source_errors=True,
        ctx=mock_ctx,
    )

    mock_handle_gare.assert_called_once_with(mock_client.submit_transfer, expected_data)
    assert res.task_id == task_id


def test_globus_transfer_submit_file_transfer_task_api_error(
    mock_ctx: Mock, mock_handle_gare: Mock
):
    mock_handle_gare.side_effect = GlobusAPIError(r=MagicMock())
    with pytest.raises(ToolError, match="Failed to submit transfer"):
        globus_transfer_submit_file_transfer_task(
            source_collection_id=str(uuid.uuid4()),
            destination_collection_id=str(uuid.uuid4()),
            items=[TransferItem(source_path=random_string(), destination_path=random_string())],
            ctx=mock_ctx,
        )


def test_globus_transfer_submit_file_transfer_task_disallowed_source(
    mock_ctx: Mock, mock_client: Mock, mock_handle_gare: Mock
):
    set_restricted_config(mock_ctx, source=(str(uuid.uuid4()),))
    with pytest.raises(ToolError, match="not permitted as a source collection"):
        globus_transfer_submit_file_transfer_task(
            source_collection_id=str(uuid.uuid4()),
            destination_collection_id=str(uuid.uuid4()),
            items=[TransferItem(source_path=random_string(), destination_path=random_string())],
            ctx=mock_ctx,
        )
    mock_handle_gare.assert_not_called()


def test_globus_transfer_submit_file_transfer_task_disallowed_destination(
    mock_ctx: Mock, mock_client: Mock, mock_handle_gare: Mock
):
    source_collection_id = str(uuid.uuid4())
    set_restricted_config(
        mock_ctx, source=(source_collection_id,), destination=(str(uuid.uuid4()),)
    )
    with pytest.raises(ToolError, match="not permitted as a destination collection"):
        globus_transfer_submit_file_transfer_task(
            source_collection_id=source_collection_id,
            destination_collection_id=str(uuid.uuid4()),
            items=[TransferItem(source_path=random_string(), destination_path=random_string())],
            ctx=mock_ctx,
        )
    mock_handle_gare.assert_not_called()


def test_globus_transfer_get_task_events(mock_ctx: Mock, mock_client: Mock):
    task_id = str(uuid.uuid4())

    res_data: dict[str, Any] = {
        "limit": random.randint(1, 1000),
        "offset": random.randint(0, 1000),
        "DATA": [],
    }
    for _ in range(random.randint(1, 10)):
        res_data["DATA"].append(
            {
                "code": random_string(),
                "is_error": False,
                "description": random_string(),
                "details": random_string(),
                "time": random_string(),
            }
        )
    mock_client.task_event_list.return_value = res_data

    res = globus_transfer_get_task_events(
        task_id=task_id, limit=res_data["limit"], offset=res_data["offset"], ctx=mock_ctx
    )

    mock_client.task_event_list.assert_called_once_with(
        task_id=task_id, limit=res_data["limit"], offset=res_data["offset"]
    )
    assert res.limit == res_data["limit"]
    assert res.offset == res_data["offset"]
    for idx, event in enumerate(res.data):
        event_data = res_data["DATA"][idx]
        assert event.code == event_data["code"]
        assert event.is_error is event_data["is_error"]
        assert event.description == event_data["description"]
        assert event.details == event_data["details"]
        assert event.time == event_data["time"]


def test_globus_transfer_get_task_events_api_error(mock_ctx: Mock, mock_client: Mock):
    mock_client.task_event_list.side_effect = GlobusAPIError(r=MagicMock())
    with pytest.raises(ToolError, match="Failed to get task events"):
        globus_transfer_get_task_events(task_id=str(uuid.uuid4()), limit=10, offset=0, ctx=mock_ctx)


def test_globus_transfer_list_directory_contents(mock_ctx: Mock, mock_client: Mock):
    collection_id = str(uuid.uuid4())
    path = random_string()

    res_data: dict[str, Any] = {
        "limit": random.randint(1, 1000),
        "offset": random.randint(0, 1000),
        "DATA": [],
    }
    for _ in range(random.randint(1, 10)):
        res_data["DATA"].append(
            {
                "name": random_string(),
                "type": random_string(),
                "link_target": random_string(),
                "user": random_string(),
                "group": random_string(),
                "permissions": random_string(),
                "size": random.randint(1, 1000),
                "last_modified": random_string(),
            }
        )
    mock_client.operation_ls.return_value = res_data

    res = globus_transfer_list_directory_contents(
        collection_id=collection_id,
        path=path,
        limit=res_data["limit"],
        offset=res_data["offset"],
        ctx=mock_ctx,
    )

    mock_client.operation_ls.assert_called_once_with(
        collection_id, path=path, limit=res_data["limit"], offset=res_data["offset"], show_hidden=True
    )
    assert res.limit == res_data["limit"]
    assert res.offset == res_data["offset"]
    for idx, file in enumerate(res.data):
        file_data = res_data["DATA"][idx]
        assert file.name == file_data["name"]
        assert file.type == file_data["type"]
        assert file.link_target == file_data["link_target"]
        assert file.user == file_data["user"]
        assert file.group == file_data["group"]
        assert file.permissions == file_data["permissions"]
        assert file.size == file_data["size"]
        assert file.last_modified == file_data["last_modified"]


def test_globus_transfer_list_directory_contents_api_error(mock_ctx: Mock, mock_client: Mock):
    mock_client.operation_ls.side_effect = GlobusAPIError(r=MagicMock())
    with pytest.raises(ToolError, match="Failed to list directory contents"):
        globus_transfer_list_directory_contents(
            collection_id=str(uuid.uuid4()), path=random_string(), limit=100, offset=0, ctx=mock_ctx
        )


def test_globus_transfer_list_directory_contents_disallowed_collection(
    mock_ctx: Mock, mock_client: Mock
):
    set_restricted_config(mock_ctx, source=(str(uuid.uuid4()),))
    with pytest.raises(ToolError, match="not permitted as a source collection"):
        globus_transfer_list_directory_contents(
            collection_id=str(uuid.uuid4()), path=random_string(), limit=100, offset=0, ctx=mock_ctx
        )
    mock_client.operation_ls.assert_not_called()


def test_globus_transfer_stat_path(mock_ctx: Mock, mock_client: Mock):
    collection_id = str(uuid.uuid4())
    path = random_string()
    file_data: dict[str, Any] = {
        "name": random_string(),
        "type": random_string(),
        "link_target": random_string(),
        "user": random_string(),
        "group": random_string(),
        "permissions": random_string(),
        "size": random.randint(1, 1000),
        "last_modified": random_string(),
    }
    mock_client.operation_stat.return_value = file_data

    res = globus_transfer_stat_path(collection_id=collection_id, path=path, ctx=mock_ctx)

    mock_client.operation_stat.assert_called_once_with(collection_id, path=path)
    assert res.name == file_data["name"]
    assert res.type == file_data["type"]
    assert res.link_target == file_data["link_target"]
    assert res.user == file_data["user"]
    assert res.group == file_data["group"]
    assert res.permissions == file_data["permissions"]
    assert res.size == file_data["size"]
    assert res.last_modified == file_data["last_modified"]


def test_globus_transfer_stat_path_api_error(mock_ctx: Mock, mock_client: Mock):
    mock_client.operation_stat.side_effect = GlobusAPIError(r=MagicMock())
    with pytest.raises(ToolError, match="Failed to stat path"):
        globus_transfer_stat_path(
            collection_id=str(uuid.uuid4()), path=random_string(), ctx=mock_ctx
        )


def test_globus_transfer_stat_path_disallowed_collection(mock_ctx: Mock, mock_client: Mock):
    set_restricted_config(mock_ctx, source=(str(uuid.uuid4()),))
    with pytest.raises(ToolError, match="not permitted as a source collection"):
        globus_transfer_stat_path(
            collection_id=str(uuid.uuid4()), path=random_string(), ctx=mock_ctx
        )
    mock_client.operation_stat.assert_not_called()


def test_globus_transfer_get_task_status(mock_ctx: Mock, mock_client: Mock):
    task_id = str(uuid.uuid4())
    task_data = {
        "task_id": task_id,
        "status": "SUCCEEDED",
        "label": random_string(),
        "bytes_transferred": random.randint(0, 10_000_000),
        "files_transferred": random.randint(0, 100),
        "files_skipped": random.randint(0, 10),
        "deadline": None,
        "completion_time": random_string(),
    }
    mock_client.get_task.return_value = Mock(data=task_data)

    res = globus_transfer_get_task_status(task_id=task_id, ctx=mock_ctx)

    mock_client.get_task.assert_called_once_with(task_id)
    assert res.task_id == task_data["task_id"]
    assert res.status == task_data["status"]
    assert res.label == task_data["label"]
    assert res.bytes_transferred == task_data["bytes_transferred"]
    assert res.files_transferred == task_data["files_transferred"]
    assert res.files_skipped == task_data["files_skipped"]
    assert res.deadline is None
    assert res.completion_time == task_data["completion_time"]


def test_globus_transfer_get_task_status_api_error(mock_ctx: Mock, mock_client: Mock):
    mock_client.get_task.side_effect = GlobusAPIError(r=MagicMock())
    with pytest.raises(ToolError, match="Failed to get task status"):
        globus_transfer_get_task_status(task_id=str(uuid.uuid4()), ctx=mock_ctx)
