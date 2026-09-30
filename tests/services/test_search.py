import uuid
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from globus_sdk import GlobusAPIError
from mcp.server.mcpserver.exceptions import ToolError

from globus_mcp.services.search.tools import (
    globus_search_get_index_field_mapping,
    globus_search_list_indices,
    globus_search_query,
)
from tests.utils import random_string, set_restricted_config


def _index(index_id: str) -> dict[str, Any]:
    return {"id": index_id, "display_name": random_string(), "status": "open"}


def _list_indices(mock_ctx: Mock, ids: list[str]):
    client = Mock()
    client.index_list.return_value.data = {"index_list": [_index(i) for i in ids]}
    with patch("globus_mcp.services.search.tools.get_search_client", return_value=client):
        return globus_search_list_indices(ctx=mock_ctx)


def test_list_indices_all_allowed_when_unrestricted(mock_ctx: Mock):
    ids = [str(uuid.uuid4()) for _ in range(3)]
    result = _list_indices(mock_ctx, ids)
    assert [i.index_id for i in result] == ids
    assert all(i.allowed for i in result)


def test_list_indices_marks_usability_without_filtering(mock_ctx: Mock):
    ok, not_ok = str(uuid.uuid4()), str(uuid.uuid4())
    set_restricted_config(mock_ctx, search=(ok,))
    result = {i.index_id: i for i in _list_indices(mock_ctx, [ok, not_ok])}
    assert set(result) == {ok, not_ok}
    assert result[ok].allowed is True
    assert result[not_ok].allowed is False


def _with_client(client: Mock):
    return patch("globus_mcp.services.search.tools.get_search_client", return_value=client)


def test_field_mapping_returns_mappings(mock_ctx: Mock):
    index_id = str(uuid.uuid4())
    client = Mock()
    client.get.return_value = {
        "@datatype": "UGFieldMappings",
        "mappings": {"dc.titles.title": "text", "files.length": "long"},
    }
    with _with_client(client):
        result = globus_search_get_index_field_mapping(index_id=index_id, ctx=mock_ctx)

    client.get.assert_called_once_with(f"/beta/index/{index_id}/mapping")
    assert result.index_id == index_id
    assert result.mappings == {"dc.titles.title": "text", "files.length": "long"}


def test_field_mapping_api_error_is_tool_error(mock_ctx: Mock):
    client = Mock()
    client.get.side_effect = GlobusAPIError(r=MagicMock())
    with _with_client(client), pytest.raises(ToolError, match="unavailable"):
        globus_search_get_index_field_mapping(index_id=str(uuid.uuid4()), ctx=mock_ctx)


@pytest.mark.parametrize("payload", [{}, {"mappings": None}, {"mappings": ["x"]}])
def test_field_mapping_unexpected_response_is_tool_error(mock_ctx: Mock, payload: dict[str, Any]):
    client = Mock()
    client.get.return_value = payload
    with _with_client(client), pytest.raises(ToolError, match="unavailable"):
        globus_search_get_index_field_mapping(index_id=str(uuid.uuid4()), ctx=mock_ctx)


def test_field_mapping_respects_whitelist(mock_ctx: Mock):
    set_restricted_config(mock_ctx, search=(str(uuid.uuid4()),))
    client = Mock()
    with _with_client(client), pytest.raises(ToolError, match="not permitted"):
        globus_search_get_index_field_mapping(index_id=str(uuid.uuid4()), ctx=mock_ctx)
    client.get.assert_not_called()


def _query_response() -> dict[str, Any]:
    return {
        "total": 2,
        "count": 2,
        "offset": 0,
        "has_next_page": False,
        "gmeta": [
            {
                "subject": "s1",
                "entries": [
                    {
                        "entry_id": None,
                        "content": {"dc": {"title": "T", "publisher": "P"}, "files": [1]},
                    }
                ],
            },
            {"subject": "s2", "entries": [{"entry_id": "e", "content": {"other": 1}}]},
        ],
    }


def _query(mock_ctx: Mock, **kwargs: Any):
    client = Mock()
    client.post_search.return_value.data = _query_response()
    with _with_client(client):
        return globus_search_query(index_id=str(uuid.uuid4()), q="x", ctx=mock_ctx, **kwargs)


def test_query_returns_full_content_by_default(mock_ctx: Mock):
    result = _query(mock_ctx)
    expected = _query_response()["gmeta"][0]["entries"][0]["content"]
    assert result.gmeta[0].entries[0].content == expected


def test_query_only_fields_limits_content(mock_ctx: Mock):
    result = _query(mock_ctx, only_fields=["dc.title"])
    assert result.gmeta[0].entries[0].content == {"dc": {"title": "T"}}


def test_query_only_fields_keeps_entries_with_no_match(mock_ctx: Mock):
    result = _query(mock_ctx, only_fields=["dc.title"])
    # Entry is retained (empty) so the caller can tell the projection was too narrow
    assert result.gmeta[1].subject == "s2"
    assert result.gmeta[1].entries[0].entry_id == "e"
    assert result.gmeta[1].entries[0].content == {}
    assert result.count == 2
