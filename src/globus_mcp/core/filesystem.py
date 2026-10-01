"""
Some MCP features involve data too big to load directly into LLM context. The solution is to share
    a path between the MCP server and the LLM agent, so that one-off scripts can process data, and
    the MCP server can directly access the results.  This is only allowed for locally deployed MCPs.

This module implements some very basic safeguards to sanity-check that filesystem path.
It is up to the user to validate their own configuration options, and to set up appropriate mount
    points for container sandbox.
"""

import os
import sys
import tempfile
from functools import cache
from pathlib import Path

# ---------------------------------------------------------------------------
# Denylist category 1: the MCP server
#
# Forbidden to read or write (parent) paths that may result in overwriting app code
# ---------------------------------------------------------------------------
_PROTECTED_PATHS: tuple[Path, ...] = (
    Path(sys.prefix).resolve(),
    Path(__file__).resolve().parents[1],
)

# ---------------------------------------------------------------------------
# Denylist category 2: FHS / OS-owned system directories (Linux and Mac)
# The MCP server is forbidden from reading/writing core system locations
#   Based on the Filesystem Hierarchy Standard and macOS equivalents.
#
# Deliberately excluded from this list — legitimate data locations:
#   /mnt, /media (removable/network mount points)
# ---------------------------------------------------------------------------
_FHS_SYSTEM_DIRS: tuple[str, ...] = (
    # Core POSIX / Linux FHS — binaries, libraries, system config, runtime
    "/bin",
    "/sbin",
    "/lib",
    "/lib32",
    "/lib64",
    "/libx32",
    "/usr",
    "/etc",
    "/boot",
    "/dev",
    "/proc",
    "/sys",
    "/root",
    "/run",
    "/var",
    "/srv",
    "/opt",
    # macOS system hierarchy
    "/System",
    "/Library",
    "/Applications",
    "/private",
)


def _overlaps(a: Path, b: Path) -> bool:
    """True if a and b are equal or one is an ancestor of the other."""
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def _hidden_segment(path: Path) -> str | None:
    """Return the first dot-prefixed path component, if any, else None."""
    for part in path.parts:
        if part not in ("/", "") and part.startswith("."):
            return part
    return None


def _check_read_write_access(root: Path) -> None:
    """
    Verify that filesystem_root is actually readable and writable.
    """
    # There are many edge cases where os.access can return misleading results (see python docs).
    #   The most reliable test is to try an operation and report the result
    try:
        next(root.iterdir(), None)
    except OSError as e:
        raise ValueError(f"FILESYSTEM_ROOT ({root}) is not readable: {e}") from e

    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix="globus_mcp_write_check_"):
            pass
    except OSError as e:
        raise ValueError(f"FILESYSTEM_ROOT ({root}) is not writable: {e}") from e


@cache
def resolve_filesystem_root() -> Path | None:
    """
    Read and validate the FILESYSTEM_ROOT environment variable.

    Returns the resolved, canonical Path if set; None if unset or empty.
    Raises ValueError with a descriptive message for any invalid configuration.

    Validation checks (in order) are best-effort safeguards to prevent the LLM from
     reading/writing sensitive system files via a crafted MCP path:
      1. Must have at least one path segment beyond '/'.
      2. Must exist and be a directory.
      3. Must not overlap with the MCP server's Python environment or source.
      4. Must not overlap with FHS / OS-owned system directories.
      5. Must not be the user home directory.
      6. Must not contain a hidden (dot-prefixed) path segment; these often contain
        sensitive data such as credentials
      7. Must be readable and writable by this process.
    """
    raw = os.environ.get("FILESYSTEM_ROOT", "").strip()
    if not raw:
        return None

    root = Path(raw).resolve()

    if root == Path("/"):
        raise ValueError(f"FILESYSTEM_ROOT must not be the filesystem root '/'. Got: {raw!r}")

    if not root.exists():
        raise ValueError(f"FILESYSTEM_ROOT path does not exist: {root}")

    if not root.is_dir():
        raise ValueError(f"FILESYSTEM_ROOT is not a directory: {root}")

    # Check 3: server code
    for protected in _PROTECTED_PATHS:
        if _overlaps(root, protected):
            raise ValueError(
                f"FILESYSTEM_ROOT ({root}) overlaps with the server's Python environment"
                f" or source code ({protected})."
                " Choose a directory outside the Python environment and server source."
            )

    # Check 4: FHS / OS system directories
    # Special exemption: on some platforms, user temp dir is allowed, even if part of an otherwise denied root
    # To avoid leaking data from other programs, users:
    # * Allow things inside the temp dir, but not the root temp folder.
    # * User must own the chosen folder
    temp_dir = Path(tempfile.gettempdir()).resolve()
    if root == temp_dir:
        raise ValueError(
            f"FILESYSTEM_ROOT must not be the system temp directory ({temp_dir})."
            " Choose a dedicated subdirectory."
        )
    in_temp_dir = root.is_relative_to(temp_dir)
    if in_temp_dir and root.stat().st_uid != os.geteuid():
        raise ValueError(
            f"FILESYSTEM_ROOT ({root}) is inside the system temp directory but is not owned"
            " by the current user."
        )

    for sysdir_str in _FHS_SYSTEM_DIRS:
        sysdir = Path(sysdir_str).resolve()
        if in_temp_dir and temp_dir.is_relative_to(sysdir):
            continue
        if _overlaps(root, sysdir):
            raise ValueError(
                f"FILESYSTEM_ROOT ({root}) overlaps with an OS system directory"
                f" ({sysdir}). Choose a directory outside the system hierarchy"
                " (see: Filesystem Hierarchy Standard)."
            )

    # Check 5: home directory
    try:
        home = Path.home()
    except RuntimeError:
        home = None  # container with no configured home directory

    if home is not None and root == home.resolve():
        raise ValueError(
            f"FILESYSTEM_ROOT must not be the user home directory ({home})."
            " Choose a dedicated subdirectory to limit the server's filesystem access."
        )

    # Check 6: hidden path segment (dotfile/dotdir), e.g. .ssh, .aws, .globus
    hidden = _hidden_segment(root)
    if hidden is not None:
        raise ValueError(
            f"FILESYSTEM_ROOT ({root}) contains a hidden path segment ({hidden!r})."
            " Hidden directories are conventionally used for credentials and"
            " application config; choose a non-hidden directory."
        )

    # Check 7: real read/write access
    _check_read_write_access(root)

    return root


def resolve_local_path(root: Path, user_path: str) -> Path:
    """
    Safely resolve user_path relative to root, enforcing that the result stays
    within root.

    MCP tools are never allowed to read or write a path that contains a hidden segment, due to
        the risk of, eg, credential exfiltration or sensitive config overwrites in a rogue tool.

    Raises ValueError if the resolved path escapes root, refers to root itself, or
    contains a hidden path segment.
    """
    relative = user_path.lstrip("/")
    if not relative:
        raise ValueError("Path must not be empty or refer only to '/'")

    resolved = (root / relative).resolve()

    if not resolved.is_relative_to(root):
        raise ValueError("Path resolves outside the permitted filesystem root.")

    if resolved == root:
        raise ValueError("Path must refer to a file, not the filesystem root itself.")

    hidden = _hidden_segment(resolved.relative_to(root))
    if hidden is not None:
        raise ValueError(
            f"Path segment {hidden!r} is a hidden file or directory, which is not"
            " permitted here. This restriction exists to reduce the risk of"
            " exfiltrating sensitive files that may have been placed in the"
            " shared filesystem root."
        )

    return resolved
