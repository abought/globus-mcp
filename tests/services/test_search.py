import uuid
from typing import Any
from unittest.mock import Mock, patch

from globus_mcp.services.search.tools import globus_search_list_indices
from tests.utils import random_string, set_restricted_config


def _index(index_id: str) -> dict[str, Any]:
    return {"id": index_id, "display_name": random_string(), "status": "open"}


def _list_indices(mock_ctx: Mock, ids: list[str]):
    client = Mock()
    client.index_list.return_value.data = {"index_list": [_index(i) for i in ids]}
    with patch("globus_mcp.services.search.tools.get_search_client", return_value=client):
        return globus_search_list_indices(mock_ctx)

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
