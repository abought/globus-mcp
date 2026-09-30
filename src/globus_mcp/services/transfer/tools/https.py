import base64
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

import globus_sdk
import httpx2
from globus_sdk.scopes import GCSCollectionScopeBuilder
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from globus_mcp.core.audit import audited, log_tool_result
from globus_mcp.core.context import GlobusContext
from globus_mcp.core.filesystem import resolve_local_path
from globus_mcp.services.transfer.client import get_transfer_client
from globus_mcp.services.transfer.schemas import (
    HttpsDownloadResponse,
    HttpsFileDownloadResponse,
    HttpsFileUploadResponse,
    HttpsUploadResponse,
)
from globus_mcp.services.transfer.whitelist import transfer_whitelist

_SERVICE = "transfer"
_LLM_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB — fits comfortably in LLM context
_DIRECT_FILE_MAX_BYTES = 100 * 1024 * 1024  # 100 MiB — cap for single-shot HTTPS transfers


def _ensure_parent_dirs(
    client: globus_sdk.TransferClient, collection_id: str, dest_path: str
) -> None:
    """
    Create any missing directory segments up to dest_path's parent.
      Although globus transfers auto-create the path, upload-via-https does not.
    """
    parent = PurePosixPath(dest_path).parent
    if str(parent) == "/":
        return

    try:
        # Fast path: parent already exists
        client.operation_stat(collection_id, path=str(parent))
        return
    except globus_sdk.GlobusAPIError as e:
        if e.http_status != HTTPStatus.NOT_FOUND:
            raise

    # Slow path: create each missing segment in order.
    for i in range(1, len(parent.parts) + 1):
        segment = str(PurePosixPath(*parent.parts[:i]))
        if segment == "/":
            continue
        try:
            client.operation_mkdir(collection_id, path=segment)
        except globus_sdk.GlobusAPIError as e:
            if e.code == "ExternalError.MkdirFailed.Exists":
                continue
            raise


def _get_https_auth_header(ctx: Context[GlobusContext], collection_id: str) -> tuple[str, str]:
    """
    Return (https_base_url, auth_header) for HTTPS operations on a collection.

    Raises ToolError if the collection does not advertise an HTTPS server.
    """
    globus_ctx = ctx.request_context.lifespan_context
    client = get_transfer_client(ctx)

    try:
        endpoint_data = client.get_endpoint(collection_id)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to get collection info: {e}") from e

    https_base_url = endpoint_data.get("https_server")
    if not https_base_url:
        raise ToolError(
            "Collection does not support HTTPS access (no https_server in endpoint data)"
        )

    https_scope = GCSCollectionScopeBuilder(collection_id).https
    globus_ctx.app.add_scope_requirements({collection_id: https_scope})
    authorizer = globus_ctx.app.get_authorizer(collection_id)
    auth_header = authorizer.get_authorization_header()
    if auth_header is None:
        raise ToolError(
            f"Failed to obtain an authorization header for collection {collection_id!r}"
        )
    return https_base_url, auth_header


def _iter_file(path: Path) -> Iterator[bytes]:
    with path.open("rb") as f:
        yield from iter(lambda: f.read(65_536), b"")


@audited(_SERVICE)
@transfer_whitelist(destination="collection_id")
def globus_transfer_direct_upload_content_via_https(
    collection_id: Annotated[str, Field(description="UUID of the Globus collection")],
    dest_path: Annotated[
        str,
        Field(
            description=(
                "Destination path on the collection, including filename"
                " (e.g. /folder/file.txt). Parent directories are created automatically."
            )
        ),
    ],
    content: Annotated[str, Field(description="File content to upload")],
    encoding: Annotated[
        Literal["utf-8", "base64"],
        Field(
            description=(
                "How 'content' is encoded."
                " 'utf-8': plain text, sent as-is."
                " 'base64': standard base64, decoded to raw bytes before upload."
                " Use 'base64' for binary files."
            )
        ),
    ] = "utf-8",
    *,
    ctx: Context[GlobusContext],
) -> HttpsUploadResponse:
    """
    Upload content directly to a file in a Globus collection via HTTPS.

    Convenience helper: Most globus transfers require both a source and a destination collection.
      Some collections allow direct file upload (via https) without a source collection.

    Limited to single files ≤ 100 MiB; use `globus_transfer_submit_file_transfer_task` for
      larger files or folders. Does not overwrite existing files.
    """

    if encoding == "base64":
        try:
            content_bytes = base64.b64decode(content)
        except Exception as e:
            raise ToolError(f"Invalid base64 content: {e}") from e
    else:
        content_bytes = content.encode("utf-8")

    if len(content_bytes) > _LLM_MAX_BYTES:
        raise ToolError(
            f"Content size {len(content_bytes):,} bytes exceeds the 1 MiB limit."
            " Use `globus_transfer_submit_file_transfer_task` for larger files."
        )

    client = get_transfer_client(ctx)

    try:
        client.operation_stat(collection_id, path=dest_path)
        raise ToolError(
            f"Destination already exists on collection: {dest_path!r}."
            " This tool does not overwrite existing files."
        )
    except globus_sdk.GlobusAPIError as e:
        if e.http_status != HTTPStatus.NOT_FOUND:
            raise ToolError(f"Failed to check destination: {e}") from e

    https_base_url, auth_header = _get_https_auth_header(ctx, collection_id)

    try:
        _ensure_parent_dirs(client, collection_id, dest_path)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to create destination directories: {e}") from e

    url = https_base_url.rstrip("/") + "/" + dest_path.lstrip("/")

    try:
        with httpx2.Client() as http_client:
            response = http_client.put(
                url,
                content=content_bytes,
                headers={"Authorization": auth_header},
            )
            response.raise_for_status()
    except httpx2.HTTPStatusError as e:
        raise ToolError(f"HTTPS upload failed ({e.response.status_code}): {e.response.text}") from e
    except httpx2.RequestError as e:
        raise ToolError(f"HTTPS request error: {e}") from e

    log_tool_result(
        ctx,
        tool_name=globus_transfer_direct_upload_content_via_https.__name__,
        service=_SERVICE,
        result={"url": url, "size_bytes": len(content_bytes)},
    )
    return HttpsUploadResponse(url=url, path=dest_path)


@audited(_SERVICE)
@transfer_whitelist(source="collection_id")
def globus_transfer_direct_read_content(
    collection_id: Annotated[str, Field(description="UUID of the Globus collection")],
    source_path: Annotated[
        str,
        Field(description="Path to the file on the collection (e.g. /folder/file.txt)"),
    ],
    *,
    ctx: Context[GlobusContext],
) -> HttpsDownloadResponse:
    """
    Directly read content from the Globus collection and return to the LLM.
    Only works for small files (<1MiB). For large files, or folders, use
      `globus_transfer_download_file_via_https` or `globus_transfer_submit_file_transfer_task`.

    Convenience helper: Most globus transfers require both a source and a destination collection.
      Some collections allow direct file access (via https) without a destination collection.
    """

    https_base_url, auth_header = _get_https_auth_header(ctx, collection_id)

    url = https_base_url.rstrip("/") + "/" + source_path.lstrip("/")

    try:
        with httpx2.Client() as http_client:
            with http_client.stream("GET", url, headers={"Authorization": auth_header}) as response:
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > _LLM_MAX_BYTES:
                    raise ToolError(
                        f"File size {int(content_length):,} bytes exceeds the 1 MiB limit."
                        " Use `globus_transfer_download_file_via_https` for larger files."
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > _LLM_MAX_BYTES:
                        raise ToolError(
                            "File exceeds the 1 MiB limit."
                            " Use `globus_transfer_download_file_via_https` for larger files."
                        )
                    chunks.append(chunk)
                content_bytes = b"".join(chunks)
    except httpx2.HTTPStatusError as e:
        raise ToolError(
            f"HTTPS download failed ({e.response.status_code}): {e.response.text}"
        ) from e
    except httpx2.RequestError as e:
        raise ToolError(f"HTTPS request error: {e}") from e

    try:
        content_str = content_bytes.decode("utf-8")
        file_encoding: Literal["utf-8", "base64"] = "utf-8"
    except UnicodeDecodeError:
        content_str = base64.b64encode(content_bytes).decode("ascii")
        file_encoding = "base64"

    log_tool_result(
        ctx,
        tool_name=globus_transfer_direct_read_content.__name__,
        service=_SERVICE,
        result={"url": url, "size_bytes": len(content_bytes), "encoding": file_encoding},
    )
    return HttpsDownloadResponse(
        content=content_str,
        encoding=file_encoding,
        size_bytes=len(content_bytes),
        url=url,
    )


@audited(_SERVICE)
@transfer_whitelist(destination="collection_id")
def globus_transfer_upload_file_via_https(
    collection_id: Annotated[str, Field(description="UUID of the Globus collection")],
    dest_path: Annotated[
        str,
        Field(
            description=(
                "Destination path on the collection, including filename"
                " (e.g. /folder/file.txt). Parent directories are created automatically."
            )
        ),
    ],
    local_path: Annotated[
        str,
        Field(
            description=(
                "Path to the local file to upload, relative to the configured filesystem root."
                " A leading '/' is ignored — paths cannot escape the root."
            )
        ),
    ],
    *,
    ctx: Context[GlobusContext],
) -> HttpsFileUploadResponse:
    """
    Upload a large local file to a Globus collection.

    This reads content from a filesystem shared by the MCP and the agent
      (see `mcp_get_shared_mount_location`).

    Convenience helper: Most globus transfers require both a source and a destination collection.
      Some collections allow direct file upload (via https) without a source collection.

    Limited to single files ≤ 100 MiB; use `globus_transfer_submit_file_transfer_task` for
      larger files or folders. Does not overwrite existing files.
    """

    filesystem_root = ctx.request_context.lifespan_context.config.filesystem_root
    assert filesystem_root is not None  # guaranteed by conditional registration

    try:
        local_file = resolve_local_path(filesystem_root, local_path)
    except ValueError as e:
        raise ToolError(str(e)) from e

    if not local_file.exists():
        raise ToolError(f"Local file does not exist: {local_path!r}")
    if not local_file.is_file():
        raise ToolError(f"Local path is not a file: {local_path!r}")

    file_size = local_file.stat().st_size
    if file_size > _DIRECT_FILE_MAX_BYTES:
        raise ToolError(
            f"Local file size {file_size:,} bytes exceeds the 100 MiB limit for this tool."
            " Use `globus_transfer_submit_file_transfer_task` for larger files."
        )

    client = get_transfer_client(ctx)

    try:
        client.operation_stat(collection_id, path=dest_path)
        raise ToolError(
            f"Destination already exists on collection: {dest_path!r}."
            " This tool does not overwrite existing files."
        )
    except globus_sdk.GlobusAPIError as e:
        if e.http_status != HTTPStatus.NOT_FOUND:
            raise ToolError(f"Failed to check destination: {e}") from e

    https_base_url, auth_header = _get_https_auth_header(ctx, collection_id)

    try:
        _ensure_parent_dirs(client, collection_id, dest_path)
    except globus_sdk.GlobusAPIError as e:
        raise ToolError(f"Failed to create destination directories: {e}") from e

    url = https_base_url.rstrip("/") + "/" + dest_path.lstrip("/")

    try:
        with httpx2.Client(timeout=None) as http_client:
            response = http_client.put(
                url,
                content=_iter_file(local_file),
                headers={"Authorization": auth_header},
            )
            response.raise_for_status()
    except httpx2.HTTPStatusError as e:
        raise ToolError(f"HTTPS upload failed ({e.response.status_code}): {e.response.text}") from e
    except httpx2.RequestError as e:
        raise ToolError(f"HTTPS request error: {e}") from e

    log_tool_result(
        ctx,
        tool_name=globus_transfer_upload_file_via_https.__name__,
        service=_SERVICE,
        result={"url": url, "local_path": str(local_file), "size_bytes": file_size},
    )
    return HttpsFileUploadResponse(
        url=url,
        collection_path=dest_path,
        local_path=str(local_file),
        size_bytes=file_size,
    )


@audited(_SERVICE)
@transfer_whitelist(source="collection_id")
def globus_transfer_download_file_via_https(
    collection_id: Annotated[str, Field(description="UUID of the Globus collection")],
    source_path: Annotated[
        str,
        Field(description="Path to the file on the collection (e.g. /folder/file.txt)"),
    ],
    local_path: Annotated[
        str | None,
        Field(
            description=(
                "Local path to save the file, relative to the configured filesystem root."
                " A leading '/' is ignored — paths cannot escape the root."
                " Defaults to the filename from source_path placed directly in the root."
            )
        ),
    ] = None,
    overwrite: Annotated[
        bool,
        Field(
            description=(
                "If False (default), raise an error if the local destination file already exists."
            )
        ),
    ] = False,
    *,
    ctx: Context[GlobusContext],
) -> HttpsFileDownloadResponse:
    """
    Directly download a file from the source Globus collection to a local filesystem location,
      without needing a destination collection. Returns a path to the file on disk, in
      a location shared by both the LLM and the MCP server. (see `mcp_get_shared_mount_location`)

    Limited to single files ≤ 100 MiB; use `globus_transfer_submit_file_transfer_task` for
      larger files or folders.
    """

    filesystem_root = ctx.request_context.lifespan_context.config.filesystem_root
    assert filesystem_root is not None  # guaranteed by conditional registration

    # Resolve the local destination, always enforcing root confinement.
    if local_path is not None:
        try:
            local_file = resolve_local_path(filesystem_root, local_path)
        except ValueError as e:
            raise ToolError(str(e)) from e
    else:
        filename = PurePosixPath(source_path).name
        if not filename:
            raise ToolError(
                "Cannot derive a local filename from source_path. Provide local_path explicitly."
            )
        try:
            local_file = resolve_local_path(filesystem_root, filename)
        except ValueError as e:
            raise ToolError(str(e)) from e

    local_file.parent.mkdir(parents=True, exist_ok=True)

    https_base_url, auth_header = _get_https_auth_header(ctx, collection_id)

    url = https_base_url.rstrip("/") + "/" + source_path.lstrip("/")
    # The LLM controls the local filesystem- overwrites are ok, but only in the download direction
    file_mode = "wb" if overwrite else "xb"
    size_bytes = 0

    try:
        with httpx2.Client(timeout=None) as http_client:
            with http_client.stream("GET", url, headers={"Authorization": auth_header}) as response:
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > _DIRECT_FILE_MAX_BYTES:
                    raise ToolError(
                        f"File size {int(content_length):,} bytes exceeds the 100 MiB limit."
                        " Use `globus_transfer_submit_file_transfer_task` for larger files."
                    )
                try:
                    f = local_file.open(file_mode)
                except FileExistsError as e:
                    raise ToolError(
                        f"Local file already exists:"
                        f" {str(local_file.relative_to(filesystem_root))!r}."
                        " Set overwrite=True to replace it."
                    ) from e
                try:
                    with f:
                        for chunk in response.iter_bytes():
                            size_bytes += len(chunk)
                            if size_bytes > _DIRECT_FILE_MAX_BYTES:
                                raise ToolError(
                                    "File exceeds the 100 MiB limit."
                                    " Use `globus_transfer_submit_file_transfer_task`"
                                    " for larger files."
                                )
                            f.write(chunk)
                except BaseException:
                    if file_mode == "xb":
                        local_file.unlink(missing_ok=True)
                    raise
    except httpx2.HTTPStatusError as e:
        raise ToolError(
            f"HTTPS download failed ({e.response.status_code}): {e.response.text}"
        ) from e
    except httpx2.RequestError as e:
        raise ToolError(f"HTTPS request error: {e}") from e

    log_tool_result(
        ctx,
        tool_name=globus_transfer_download_file_via_https.__name__,
        service=_SERVICE,
        result={"url": url, "local_path": str(local_file), "size_bytes": size_bytes},
    )
    return HttpsFileDownloadResponse(
        url=url,
        collection_path=source_path,
        local_path=str(local_file),
        size_bytes=size_bytes,
    )
