import uuid

import pytest

from globus_mcp.core.fields import _parse_uuid_list


class TestParseUuidList:
    def test_non_string_passes_through_unchanged(self):
        assert _parse_uuid_list(None) is None
        value = (str(uuid.uuid4()),)
        assert _parse_uuid_list(value) is value

    def test_empty_string_returns_none(self):
        assert _parse_uuid_list("   ") is None

    def test_single_id_is_parsed(self):
        cid = str(uuid.uuid4())
        assert _parse_uuid_list(cid) == (cid,)

    def test_multiple_ids_are_parsed_and_whitespace_trimmed(self):
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        assert _parse_uuid_list(f" {a} , {b} ") == (a, b)

    def test_only_commas_and_whitespace_raises(self):
        """A typo'd value (e.g. ' , , ') must fail loudly rather than silently mean
        'unrestricted' — that would defeat the purpose of setting it at all."""
        with pytest.raises(ValueError, match="no usable entries"):
            _parse_uuid_list(" , , ")

    @pytest.mark.parametrize(
        "malformed",
        [
            pytest.param("not-a-uuid", id="not_uuid_shaped"),
            pytest.param("dba0d7c0-1f63-44d1-bcd0", id="truncated_uuid"),
            pytest.param("My Collection", id="display_name_not_id"),
        ],
    )
    def test_malformed_uuid_entry_raises(self, malformed: str):
        """A non-UUID entry can never match a real ID, so it would otherwise fail silently
        (the list just becomes more restrictive than intended, with no indication anything
        is wrong). Reject it outright instead."""
        with pytest.raises(ValueError, match="not a valid UUID"):
            _parse_uuid_list(malformed)

    def test_one_malformed_entry_among_valid_ones_still_raises(self):
        with pytest.raises(ValueError, match="not a valid UUID"):
            _parse_uuid_list(f"{uuid.uuid4()},not-a-uuid")
