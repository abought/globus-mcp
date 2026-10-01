import os
import tempfile
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


def _denylisted(path: str) -> bool:
    """Literal (no filesystem access, so host-independent) check against the real denylist."""
    return any(fs._overlaps(Path(path), Path(d)) for d in fs._FHS_SYSTEM_DIRS)


class TestSystemDirDenylistContents:
    """The shipped denylist must cover both Linux and macOS, whichever one runs the tests."""

    @pytest.mark.parametrize(
        "path",
        [
            "/etc/shared",
            "/usr/local/data",
            "/var/lib/data",
            "/opt/data",
            "/root/data",
            "/proc",
            "/sys/kernel",
            "/run/user/1000",
        ],
    )
    def test_linux_system_locations_denied(self, path: str):
        assert _denylisted(path)

    @pytest.mark.parametrize(
        "path",
        [
            "/System/Library/data",
            "/Library/Application Support/x",
            "/Applications/Foo.app/data",
            "/private/etc/data",
            # macOS TMPDIR, and so pytest's tmp_path: users must pick a root elsewhere
            "/private/var/folders/zz/abc123/T/pytest-of-user/pytest-0/shared",
            "/var/folders/zz/abc123/T/shared",
        ],
    )
    def test_macos_system_locations_denied(self, path: str):
        assert _denylisted(path)

    @pytest.mark.parametrize(
        "path",
        [
            "/tmp/pytest-of-user/pytest-0/shared",  # Linux tmp_path
            "/home/user/shared",
            "/mnt/data",
            "/media/user/disk/data",
            "/Users/user/shared",
            "/Volumes/External/data",
            "/data/shared",
        ],
    )
    def test_legitimate_data_locations_allowed(self, path: str):
        assert not _denylisted(path)


class TestSystemDirDenylistBehavior:
    """
    Exercise resolve_filesystem_root's denylist handling against a synthetic filesystem layout
    under tmp_path, standing in for Linux and macOS conventions regardless of the host OS.
    """

    def _deny(self, monkeypatch: pytest.MonkeyPatch, *dirs: Path) -> None:
        monkeypatch.setattr(fs, "_FHS_SYSTEM_DIRS", tuple(str(d) for d in dirs))

    def test_linux_style_root_under_system_dir_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        etc = tmp_path / "etc"
        root = etc / "shared"
        root.mkdir(parents=True)
        self._deny(monkeypatch, etc)
        _set_root(monkeypatch, root)
        with pytest.raises(ValueError, match="OS system directory"):
            fs.resolve_filesystem_root()

    def test_root_that_is_ancestor_of_system_dir_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """Choosing a parent of a system dir would expose it, so overlap is two-way"""
        (tmp_path / "usr").mkdir()
        self._deny(monkeypatch, tmp_path / "usr")
        _set_root(monkeypatch, tmp_path)
        with pytest.raises(ValueError, match="OS system directory"):
            fs.resolve_filesystem_root()

    def test_linux_style_root_outside_system_dirs_allowed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        (tmp_path / "etc").mkdir()
        root = tmp_path / "mnt" / "data"
        root.mkdir(parents=True)
        self._deny(monkeypatch, tmp_path / "etc", tmp_path / "usr")
        _set_root(monkeypatch, root)
        assert fs.resolve_filesystem_root() == root.resolve()

    def test_macos_style_symlinked_system_dir_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """On macOS /var is a symlink to /private/var. A root named via either spelling must be
        rejected, whichever form the denylist and the user's path happen to use."""
        real = tmp_path / "private" / "var" / "folders" / "xx" / "T" / "shared"
        real.mkdir(parents=True)
        (tmp_path / "var").symlink_to(tmp_path / "private" / "var", target_is_directory=True)
        self._deny(monkeypatch, tmp_path / "var", tmp_path / "private")

        for spelling in (real, tmp_path / "var" / "folders" / "xx" / "T" / "shared"):
            _set_root(monkeypatch, spelling)
            with pytest.raises(ValueError, match="OS system directory"):
                fs.resolve_filesystem_root()

    def test_macos_style_symlink_into_system_dir_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """A harmless-looking path that resolves into a system dir is still denied."""
        private = tmp_path / "private"
        private.mkdir()
        link = tmp_path / "tmp"
        link.symlink_to(private, target_is_directory=True)
        self._deny(monkeypatch, private)
        _set_root(monkeypatch, link)
        with pytest.raises(ValueError, match="OS system directory"):
            fs.resolve_filesystem_root()

    def test_macos_style_user_dir_allowed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        (tmp_path / "private").mkdir()
        root = tmp_path / "Users" / "someone" / "shared"
        root.mkdir(parents=True)
        self._deny(monkeypatch, tmp_path / "private", tmp_path / "System")
        _set_root(monkeypatch, root)
        assert fs.resolve_filesystem_root() == root.resolve()


class TestTempDirRoots:
    """
    A root strictly inside the user's temp dir is allowed even where that dir sits in a
    denylisted tree (macOS), provided it is owned by the user. The temp dir itself is not.
    The temp dir location is simulated, so these hold on any host.
    """

    @pytest.fixture
    def macos_layout(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
        """/var -> /private/var, TMPDIR in /var/folders/xx/T; /private and /var denylisted."""
        temp = tmp_path / "private" / "var" / "folders" / "xx" / "T"
        temp.mkdir(parents=True)
        (tmp_path / "var").symlink_to(tmp_path / "private" / "var", target_is_directory=True)
        monkeypatch.setattr(
            fs, "_FHS_SYSTEM_DIRS", (str(tmp_path / "var"), str(tmp_path / "private"))
        )
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "var/folders/xx/T"))
        return temp

    def test_macos_child_of_temp_allowed(self, monkeypatch: pytest.MonkeyPatch, macos_layout: Path):
        root = macos_layout / "shared"
        root.mkdir()
        _set_root(monkeypatch, root)
        assert fs.resolve_filesystem_root() == root.resolve()

    def test_macos_deeply_nested_child_of_temp_allowed(
        self, monkeypatch: pytest.MonkeyPatch, macos_layout: Path
    ):
        root = macos_layout / "pytest-of-user" / "pytest-0" / "shared"
        root.mkdir(parents=True)
        _set_root(monkeypatch, root)
        assert fs.resolve_filesystem_root() == root.resolve()

    def test_temp_dir_itself_rejected(self, monkeypatch: pytest.MonkeyPatch, macos_layout: Path):
        _set_root(monkeypatch, macos_layout)
        with pytest.raises(ValueError, match="system temp directory"):
            fs.resolve_filesystem_root()

    def test_ancestor_of_temp_dir_rejected(
        self, monkeypatch: pytest.MonkeyPatch, macos_layout: Path
    ):
        _set_root(monkeypatch, macos_layout.parent)
        with pytest.raises(ValueError, match="OS system directory"):
            fs.resolve_filesystem_root()

    def test_sibling_of_temp_dir_in_system_tree_rejected(
        self, monkeypatch: pytest.MonkeyPatch, macos_layout: Path
    ):
        root = macos_layout.parent / "other"
        root.mkdir()
        _set_root(monkeypatch, root)
        with pytest.raises(ValueError, match="OS system directory"):
            fs.resolve_filesystem_root()

    def test_exemption_does_not_cover_unrelated_system_dir(
        self, monkeypatch: pytest.MonkeyPatch, macos_layout: Path, tmp_path: Path
    ):
        etc = tmp_path / "etc"
        etc.mkdir()
        monkeypatch.setattr(fs, "_FHS_SYSTEM_DIRS", (*fs._FHS_SYSTEM_DIRS, str(etc)))
        _set_root(monkeypatch, etc)
        with pytest.raises(ValueError, match="OS system directory"):
            fs.resolve_filesystem_root()

    def test_child_of_temp_via_symlinked_spelling_allowed(
        self, monkeypatch: pytest.MonkeyPatch, macos_layout: Path, tmp_path: Path
    ):
        (macos_layout / "shared").mkdir()
        _set_root(monkeypatch, tmp_path / "var" / "folders" / "xx" / "T" / "shared")
        assert fs.resolve_filesystem_root() == (macos_layout / "shared").resolve()

    def test_child_of_temp_not_owned_by_user_rejected(
        self, monkeypatch: pytest.MonkeyPatch, macos_layout: Path
    ):
        """Shared multi-user temp dirs: another user's directory is not an acceptable root"""
        root = macos_layout / "shared"
        root.mkdir()
        monkeypatch.setattr(os, "geteuid", lambda: root.stat().st_uid + 1)
        _set_root(monkeypatch, root)
        with pytest.raises(ValueError, match="not owned by the current user"):
            fs.resolve_filesystem_root()

    def test_linux_style_child_of_temp_allowed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """/tmp is not denylisted on Linux; the exemption is simply not needed"""
        temp = tmp_path / "tmp"
        root = temp / "shared"
        root.mkdir(parents=True)
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(temp))
        _set_root(monkeypatch, root)
        assert fs.resolve_filesystem_root() == root.resolve()

    def test_linux_style_temp_dir_itself_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        temp = tmp_path / "tmp"
        temp.mkdir()
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(temp))
        _set_root(monkeypatch, temp)
        with pytest.raises(ValueError, match="system temp directory"):
            fs.resolve_filesystem_root()


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
