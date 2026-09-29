import os
from pathlib import Path

import pytest

from globus_mcp.core import filesystem as fs


def _set_root(monkeypatch: pytest.MonkeyPatch, path: Path | str) -> None:
    monkeypatch.setenv("FILESYSTEM_ROOT", str(path))


class TestOverlaps:
    def test_equal_paths_overlap(self, tmp_path: Path):
        assert fs._overlaps(tmp_path, tmp_path) is True

    def test_child_overlaps_parent(self, tmp_path: Path):
        child = tmp_path / "child"
        assert fs._overlaps(child, tmp_path) is True

    def test_parent_overlaps_child(self, tmp_path: Path):
        child = tmp_path / "child"
        assert fs._overlaps(tmp_path, child) is True

    def test_unrelated_paths_do_not_overlap(self, tmp_path: Path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        assert fs._overlaps(a, b) is False


class TestHiddenSegment:
    def test_no_hidden_segment_returns_none(self):
        assert fs._hidden_segment(Path("/data/results/file.txt")) is None

    def test_hidden_segment_at_start(self):
        assert fs._hidden_segment(Path("/home/user/.ssh/id_rsa")) == ".ssh"

    def test_hidden_segment_in_middle(self):
        assert fs._hidden_segment(Path("a/.config/app.yaml")) == ".config"

    def test_hidden_segment_at_end(self):
        assert fs._hidden_segment(Path("a/b/.env")) == ".env"

    def test_relative_path_with_no_segments_is_not_hidden(self):
        assert fs._hidden_segment(Path(".")) is None


class TestResolveFilesystemRoot:
    def test_unset_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FILESYSTEM_ROOT", raising=False)
        assert fs.resolve_filesystem_root() is None

    def test_empty_string_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        _set_root(monkeypatch, "   ")
        assert fs.resolve_filesystem_root() is None

    def test_valid_root_is_returned_resolved(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        root = tmp_path / "shared"
        root.mkdir()
        _set_root(monkeypatch, root)
        assert fs.resolve_filesystem_root() == root.resolve()

    def test_write_check_leaves_no_litter(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        root = tmp_path / "shared"
        root.mkdir()
        _set_root(monkeypatch, root)
        fs.resolve_filesystem_root()
        assert list(root.iterdir()) == []

    def test_root_slash_rejected(self, monkeypatch: pytest.MonkeyPatch):
        _set_root(monkeypatch, "/")
        with pytest.raises(ValueError, match="filesystem root '/'"):
            fs.resolve_filesystem_root()

    def test_nonexistent_path_rejected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        _set_root(monkeypatch, tmp_path / "does-not-exist")
        with pytest.raises(ValueError, match="does not exist"):
            fs.resolve_filesystem_root()

    def test_file_not_directory_rejected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        file_path = tmp_path / "a_file"
        file_path.write_text("x")
        _set_root(monkeypatch, file_path)
        with pytest.raises(ValueError, match="not a directory"):
            fs.resolve_filesystem_root()

    def test_root_equal_to_real_venv_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        _set_root(monkeypatch, fs._PROTECTED_PATHS[0])
        with pytest.raises(ValueError, match="Python environment"):
            fs.resolve_filesystem_root()

    def test_child_of_real_source_dir_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        package_dir = fs._PROTECTED_PATHS[1]
        _set_root(monkeypatch, package_dir / "core")
        with pytest.raises(ValueError, match="Python environment"):
            fs.resolve_filesystem_root()

    def test_ancestor_of_real_source_dir_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """Source must not be reachable via specially crafted path from root"""
        _set_root(monkeypatch, fs._PROTECTED_PATHS[1].parent)
        with pytest.raises(ValueError, match="Python environment"):
            fs.resolve_filesystem_root()

    def test_root_equal_to_home_rejected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Sets the real HOME env var rather than patching Path.home() itself — this
        is the actual, documented mechanism Path.home() reads from."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))

        _set_root(monkeypatch, home)
        with pytest.raises(ValueError, match="home directory"):
            fs.resolve_filesystem_root()

    def test_missing_home_directory_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """Some system/container user accounts may not define a home directory"""

        def _raise() -> Path:
            raise RuntimeError("no home directory configured")

        monkeypatch.setattr(Path, "home", _raise)
        root = tmp_path / "shared"
        root.mkdir()
        _set_root(monkeypatch, root)
        assert fs.resolve_filesystem_root() == root.resolve()

    @pytest.mark.parametrize(
        "relative",
        [
            pytest.param(".hidden", id="root_itself_hidden"),
            pytest.param(".secret/shared", id="hidden_ancestor_of_root"),
        ],
    )
    def test_hidden_segment_in_root_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, relative: str
    ):
        root = tmp_path / relative
        root.mkdir(parents=True)
        _set_root(monkeypatch, root)
        with pytest.raises(ValueError, match="hidden path segment"):
            fs.resolve_filesystem_root()

    def test_dotted_but_not_hidden_root_is_allowed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        root = tmp_path / "my.shared.folder"
        root.mkdir()
        _set_root(monkeypatch, root)
        assert fs.resolve_filesystem_root() == root.resolve()

    def test_unwritable_root_rejected(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        if os.geteuid() == 0:
            pytest.skip("root can bypass permission bits")
        root = tmp_path / "readonly"
        root.mkdir(mode=0o500)
        _set_root(monkeypatch, root)
        try:
            with pytest.raises(ValueError, match="not writable"):
                fs.resolve_filesystem_root()
        finally:
            root.chmod(0o700)  # allow tmp_path cleanup


class TestResolveLocalPath:
    def test_simple_relative_path_resolves_inside_root(self, tmp_path: Path):
        resolved = fs.resolve_local_path(tmp_path, "a/b.txt")
        assert resolved == tmp_path / "a" / "b.txt"

    def test_leading_slash_is_stripped_not_treated_as_absolute(self, tmp_path: Path):
        resolved = fs.resolve_local_path(tmp_path, "/etc/passwd")
        assert resolved == tmp_path / "etc" / "passwd"
        assert resolved != Path("/etc/passwd")

    def test_dot_dot_traversal_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="outside"):
            fs.resolve_local_path(tmp_path, "../../etc/passwd")

    def test_empty_path_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="empty"):
            fs.resolve_local_path(tmp_path, "")

    def test_path_referring_only_to_slash_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="empty"):
            fs.resolve_local_path(tmp_path, "/")

    def test_path_equal_to_root_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="filesystem root itself"):
            fs.resolve_local_path(tmp_path, ".")

    def test_symlink_escaping_root_rejected(self, tmp_path: Path):
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (root / "escape").symlink_to(outside, target_is_directory=True)

        with pytest.raises(ValueError, match="outside"):
            fs.resolve_local_path(root, "escape/secret.txt")

    def test_symlink_within_root_is_allowed(self, tmp_path: Path):
        root = tmp_path / "root"
        real_dir = root / "real"
        real_dir.mkdir(parents=True)
        (root / "alias").symlink_to(real_dir, target_is_directory=True)

        resolved = fs.resolve_local_path(root, "alias/data.txt")
        assert resolved == (real_dir / "data.txt")

    @pytest.mark.parametrize(
        "relative",
        [
            pytest.param(".env", id="hidden_file_at_top"),
            pytest.param(".ssh/id_rsa", id="hidden_dir_then_file"),
            pytest.param("sub/.git/config", id="hidden_dir_nested"),
        ],
    )
    def test_hidden_segment_rejected(self, tmp_path: Path, relative: str):
        with pytest.raises(ValueError, match="hidden file or directory"):
            fs.resolve_local_path(tmp_path, relative)

    @pytest.mark.parametrize(
        "relative",
        [
            pytest.param("results.v2.tar.gz", id="dotted_filename"),
            pytest.param("my.dataset/file.csv", id="dotted_directory"),
        ],
    )
    def test_dotted_but_not_hidden_path_is_allowed(self, tmp_path: Path, relative: str):
        resolved = fs.resolve_local_path(tmp_path, relative)
        assert resolved == tmp_path / relative

    def test_hidden_segment_reached_via_symlink_is_rejected(self, tmp_path: Path):
        """The hidden-segment check must run on the resolved (real) path, not the
        literal input string: a non-hidden-looking path that resolves, via a symlink,
        into a hidden directory must still be rejected."""
        root = tmp_path / "root"
        root.mkdir()
        secret_dir = root / ".secret_dir"
        secret_dir.mkdir()
        (secret_dir / "data.txt").write_text("shh")
        (root / "alias").symlink_to(secret_dir, target_is_directory=True)

        with pytest.raises(ValueError, match="hidden file or directory"):
            fs.resolve_local_path(root, "alias/data.txt")
