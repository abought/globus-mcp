import uuid

import pytest

from globus_mcp.services.transfer.config import TransferConfig
from globus_mcp.services.transfer.whitelist import check_destination_allowed, check_source_allowed


class TestUnrestricted:
    """With no whitelist configured, every collection is allowed in every role."""

    def test_check_source_allowed_does_not_raise(self):
        check_source_allowed(TransferConfig(), str(uuid.uuid4()))  # no raise

    def test_check_destination_allowed_does_not_raise(self):
        check_destination_allowed(TransferConfig(), str(uuid.uuid4()))  # no raise

    def test_err_false_returns_true(self):
        assert check_source_allowed(TransferConfig(), str(uuid.uuid4()), err=False) is True
        assert check_destination_allowed(TransferConfig(), str(uuid.uuid4()), err=False) is True


class TestRestricted:
    def test_source_and_destination_are_independent(self):
        source_id = str(uuid.uuid4())
        dest_id = str(uuid.uuid4())
        config = TransferConfig(source_whitelist=(source_id,), destination_whitelist=(dest_id,))

        check_source_allowed(config, source_id)  # no raise
        check_destination_allowed(config, dest_id)  # no raise

        with pytest.raises(ValueError, match="not permitted as a destination collection"):
            check_destination_allowed(config, source_id)
        with pytest.raises(ValueError, match="not permitted as a source collection"):
            check_source_allowed(config, dest_id)

    def test_check_source_allowed_raises_for_disallowed_id(self):
        config = TransferConfig(source_whitelist=(str(uuid.uuid4()),))
        with pytest.raises(ValueError, match="not permitted as a source collection"):
            check_source_allowed(config, str(uuid.uuid4()))

    def test_check_destination_allowed_raises_for_disallowed_id(self):
        config = TransferConfig(destination_whitelist=(str(uuid.uuid4()),))
        with pytest.raises(ValueError, match="not permitted as a destination collection"):
            check_destination_allowed(config, str(uuid.uuid4()))
