from pathlib import Path

import pytest

from globus_mcp.core.config import ServerConfig, load_server_config


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FILESYSTEM_ROOT", raising=False)
    monkeypatch.delenv("GLOBUS_TRANSFER_ALLOWED_SOURCE_COLLECTIONS", raising=False)
    monkeypatch.delenv("GLOBUS_TRANSFER_ALLOWED_DESTINATION_COLLECTIONS", raising=False)


def test_load_server_config_defaults():
    config = load_server_config()
    assert isinstance(config, ServerConfig)
    assert config.filesystem_root is None
    assert config.transfer.source_whitelist is None
    assert config.transfer.destination_whitelist is None


def test_load_server_config_reads_filesystem_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    root = tmp_path / "shared"
    root.mkdir()
    monkeypatch.setenv("FILESYSTEM_ROOT", str(root))
    config = load_server_config()
    assert config.filesystem_root == root.resolve()


def test_single_bad_setting_raises_exception_group(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GLOBUS_TRANSFER_ALLOWED_SOURCE_COLLECTIONS", "not-a-uuid")
    with pytest.raises(ExceptionGroup) as exc_info:
        load_server_config()
    assert len(exc_info.value.exceptions) == 1


def test_multiple_bad_settings_are_all_reported_together(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The whole point of aggregating: a sysadmin with two unrelated typos (a bad
    FILESYSTEM_ROOT and a bad collection allowlist) should see both at once, not just the
    first one that happens to be checked."""
    monkeypatch.setenv("FILESYSTEM_ROOT", str(tmp_path / "does-not-exist"))
    monkeypatch.setenv("GLOBUS_TRANSFER_ALLOWED_SOURCE_COLLECTIONS", "not-a-uuid")

    with pytest.raises(ExceptionGroup) as exc_info:
        load_server_config()

    assert len(exc_info.value.exceptions) == 2
    messages = [str(e) for e in exc_info.value.exceptions]
    assert any("does not exist" in m for m in messages)
    assert any("not a valid UUID" in m for m in messages)
