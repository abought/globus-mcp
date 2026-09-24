import base64
from collections.abc import Callable
from http import HTTPStatus
from typing import Annotated, Any, Literal

import globus_sdk
import httpx2
from globus_sdk.scopes import GCSCollectionScopeBuilder
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from globus_mcp.audit import log_tool_call, log_tool_error, log_tool_result
from globus_mcp.categories import ToolCategory
from globus_mcp.context import GlobusContext
from globus_mcp.services.transfer.client import get_transfer_client
from globus_mcp.services.transfer.schemas import (
    HttpsDownloadResponse,
    HttpsUploadResponse,
    TransferCollectionList,
    TransferEndpoint,
    TransferEvent,
    TransferEventList,
    TransferFile,
    TransferFileList,
    TransferItem,
    TransferSubmitResponse,
    TransferTask,
)

_SERVICE = "transfer"


def _handle_gare(
    client_method: Callable[..., globus_sdk.GlobusHTTPResponse],
    *args: Any,
    **kwargs: Any,
) -> globus_sdk.GlobusHTTPResponse:
    client: globus_sdk.TransferClient = client_method.__self__  # type: ignore[attr-defined]
    try:
        return client_method(*args, **kwargs)
    except globus_sdk.GlobusAPIError as e:
        if e.http_status == HTTPStatus.FORBIDDEN and e.code == "ConsentRequired":
            scopes = e.info.consent_required.required_scopes
            for scope in scopes:
                client.add_app_scope(scope)
            return client_method(*args, **kwargs)
        raise


def _format_search_response(res: globus_sdk.IterableTransferResponse) -> TransferCollectionList:
    endpoints = []
    for e in res["DATA"]:
        endpoint = TransferEndpoint(
            endpoint_id=e["id"],
            display_name=e["display_name"],
            owner_id=e["owner_id"],
            owner_string=e["owner_string"],
            type=e["entity_type"],
            description=e.get("description"),
        )
        endpoints.append(endpoint)
    return TransferCollectionList(
        limit=res["limit"],
        offset=res["offset"],
        has_next_page=res["has_next_page"],
        data=endpoints,
    )


def globus_transfer_list_collections(
    filter_scope: Annotated[
        Literal[
            "my-endpoints",
            "administered-by-me",
            "shared-with-me",
            "shared-by-me",
            "recently-used",
            "in-use",
        ],
        Field(
            description=(
                "String indicating which scope/class of collections to list."
                " Options:"
                " my-endpoints (owned by the user),"
                " administered-by-me (user has admin role, superset of my-endpoints),"
                " shared-with-me (shared with user),"
                " shared-by-me (guest collections where user is admin or access manager),"
                " recently-used (default; recently used by user),"
                " in-use (with active tasks owned by user),"
            ),
        ),
    ] = "my-endpoints",
    limit: Annotated[int, Field(le=100, description="Maximum number of results to return.")] = 100,
    offset: Annotated[int, Field(description="Zero based offset into the result set.")] = 0,
    *,
    ctx: Context[GlobusContext],
) -> TransferCollectionList:
    """List Globus Transfer collections (storage locations) that the user has access to."""
    log_tool_call(ctx, tool_name=globus_transfer_list_collections.__name__, service=_SERVICE)
    client = get_transfer_client(ctx)

    try:
        res = client.endpoint_search(
            filter_scope=filter_scope,
            limit=limit,
            offset=offset,
        )
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx, tool_name=globus_transfer_list_collections.__name__, service=_SERVICE, error=e
        )
        raise ToolError(f"Failed to get search results: {e}") from e

    return _format_search_response(res)


def globus_transfer_search_collections(
    filter_fulltext: Annotated[
        str,
        Field(min_length=1, description="String to match collection fields against."),
    ],
    limit: Annotated[int, Field(le=100, description="Maximum number of results to return.")] = 100,
    offset: Annotated[int, Field(description="Zero based offset into the result set.")] = 0,
    *,
    ctx: Context[GlobusContext],
) -> TransferCollectionList:
    """
    Find any (user-visible) Globus collection where any field matches the specified filter string.
    """
    log_tool_call(ctx, tool_name=globus_transfer_search_collections.__name__, service=_SERVICE)
    client = get_transfer_client(ctx)

    try:
        res = client.endpoint_search(
            # TODO: Add better filter scopes etc
            filter_scope="all",
            filter_fulltext=filter_fulltext,
            limit=limit,
            offset=offset,
        )
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx, tool_name=globus_transfer_search_collections.__name__, service=_SERVICE, error=e
        )
        raise ToolError(f"Failed to get search results: {e}") from e

    return _format_search_response(res)


def globus_transfer_submit_file_transfer_task(
    source_collection_id: Annotated[str, Field(description="UUID of the source collection")],
    destination_collection_id: Annotated[
        str, Field(description="UUID of the destination collection")
    ],
    items: Annotated[
        list[TransferItem],
        Field(min_length=1, description="One or more files or directories to transfer."),
    ],
    label: Annotated[
        str,
        Field(description="Label for the transfer task"),
    ] = "Globus MCP Transfer",
    sync_level: Annotated[
        Literal["exists", "size", "mtime", "checksum"] | None,
        Field(
            description=(
                "Skip transferring files that have not changed at the destination."
                " 'exists': skip if destination file is present."
                " 'size': skip if file sizes match."
                " 'mtime': skip if source is not newer."
                " 'checksum': skip if checksums match (most reliable, slowest)."
            ),
        ),
    ] = 'checksum',

    verify_checksum: Annotated[
        bool,
        Field(
            description=(
                "After transfer, verify source and destination checksums match."
                " Failed checksums trigger a retry. Adds CPU load on both endpoints."
            ),
        ),
    ] = False,
    skip_source_errors: Annotated[
        bool,
        Field(
            description=(
                "When True, silently skip source files that are missing or permission-denied"
                " rather than failing the task. Use for large transfers over messy data catalogs."
            ),
        ),
    ] = False,
    *,
    ctx: Context[GlobusContext],
) -> TransferSubmitResponse:
    """
    Submit a transfer task to move files or folders between two Globus Transfer collections.

    Use `globus_transfer_get_task_status` to monitor the task's progress.
    """
    log_tool_call(
        ctx, tool_name=globus_transfer_submit_file_transfer_task.__name__, service=_SERVICE
    )
    client = get_transfer_client(ctx)

    data = globus_sdk.TransferData(
        # user configurable options
        source_endpoint=source_collection_id,
        destination_endpoint=destination_collection_id,
        label=label,
        sync_level=sync_level,
        verify_checksum=verify_checksum,
        skip_source_errors=skip_source_errors,  # big real transfers may have partial faulures
        # Hardcoded policies for LLM usage: make actions and failures obvious, and secure by default
        encrypt_data=True,
        fail_on_quota_errors=True,  # LLM can't intervene to fix out of band
        delete_destination_extra=False,  # powerful feature with side effects; don't expose to LLM
        notify_on_succeeded=True,
        notify_on_failed=True,
        notify_on_inactive=True,
    )
    for item in items:
        data.add_item(
            source_path=item.source_path,
            destination_path=item.destination_path,
            recursive=item.recursive,
        )

    try:
        res = _handle_gare(client.submit_transfer, data)
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx,
            tool_name=globus_transfer_submit_file_transfer_task.__name__,
            service=_SERVICE,
            error=e,
        )
        raise ToolError(f"Failed to submit transfer: {e}") from e

    task_id = res.data["task_id"]
    log_tool_result(
        ctx,
        tool_name=globus_transfer_submit_file_transfer_task.__name__,
        service=_SERVICE,
        result={"task_id": task_id},
    )
    return TransferSubmitResponse(task_id=task_id)


def globus_transfer_get_task_status(
    task_id: Annotated[str, Field(description="UUID of the transfer task")],
    *,
    ctx: Context[GlobusContext],
) -> TransferTask:
    """
    Get the status and progress of a Globus Transfer task.

    Use this to check whether a task is ACTIVE, SUCCEEDED, FAILED, or INACTIVE, and to
    monitor byte and file counts during an in-progress transfer.
    """
    log_tool_call(ctx, tool_name=globus_transfer_get_task_status.__name__, service=_SERVICE)
    client = get_transfer_client(ctx)

    try:
        res = client.get_task(task_id)
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx, tool_name=globus_transfer_get_task_status.__name__, service=_SERVICE, error=e
        )
        raise ToolError(f"Failed to get task status: {e}") from e

    d = res.data
    result = TransferTask(
        task_id=d["task_id"],
        status=d["status"],
        label=d.get("label"),
        bytes_transferred=d.get("bytes_transferred"),
        files_transferred=d.get("files_transferred"),
        files_skipped=d.get("files_skipped"),
        deadline=d.get("deadline"),
        completion_time=d.get("completion_time"),
    )
    log_tool_result(
        ctx,
        tool_name=globus_transfer_get_task_status.__name__,
        service=_SERVICE,
        result={"task_id": result.task_id, "status": result.status},
    )
    return result


def globus_transfer_get_task_events(
    task_id: Annotated[str, Field(description="UUID of the task")],
    limit: Annotated[int, Field(le=1_000, description="Maximum number of results to return.")] = 10,
    offset: Annotated[int, Field(description="Zero based offset into the result set.")] = 0,
    *,
    ctx: Context[GlobusContext],
) -> TransferEventList:
    """
    Get a list of Globus Transfer task events to monitor the status and progress of a task.
    The events are ordered by time descending (newest first).
    """
    log_tool_call(ctx, tool_name=globus_transfer_get_task_events.__name__, service=_SERVICE)
    client = get_transfer_client(ctx)

    try:
        res = client.task_event_list(task_id=task_id, limit=limit, offset=offset)
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx, tool_name=globus_transfer_get_task_events.__name__, service=_SERVICE, error=e
        )
        raise ToolError(f"Failed to get task events: {e}") from e

    events = []
    for ev in res["DATA"]:
        event = TransferEvent(
            code=ev["code"],
            is_error=ev["is_error"],
            description=ev["description"],
            details=ev["details"],
            time=ev["time"],
        )
        events.append(event)

    return TransferEventList(limit=res["limit"], offset=res["offset"], data=events)


def globus_transfer_list_directory_contents(
    collection_id: Annotated[str, Field(description="UUID of the collection")],
    path: Annotated[str, Field(description="Path to a directory")],
    limit: Annotated[
        int, Field(le=100_000, description="Maximum number of results to return.")
    ] = 100,
    offset: Annotated[int, Field(description="Zero based offset into the result set.")] = 0,
    show_hidden: Annotated[
        bool,
        Field(description="Include files and directories whose names begin with a dot."),
    ] = True,
    *,
    ctx: Context[GlobusContext],
) -> TransferFileList:
    """List contents of a directory on a Globus Transfer collection. Note: Not recursive."""
    log_tool_call(ctx, tool_name=globus_transfer_list_directory_contents.__name__, service=_SERVICE)
    client = get_transfer_client(ctx)

    try:
        # TODO: Expose filter param in the future when a clean LLM-facing syntax is defined
        res = client.operation_ls(
            collection_id, path=path, limit=limit, offset=offset, show_hidden=show_hidden
        )
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx,
            tool_name=globus_transfer_list_directory_contents.__name__,
            service=_SERVICE,
            error=e,
        )
        raise ToolError(f"Failed to list directory contents: {e}") from e

    files = []
    for f in res["DATA"]:
        file = TransferFile(
            name=f["name"],
            type=f["type"],
            link_target=f.get("link_target"),
            user=f.get("user"),
            group=f.get("group"),
            permissions=f["permissions"],
            size=f["size"],
            last_modified=f["last_modified"],
        )
        files.append(file)

    return TransferFileList(limit=limit, offset=offset, data=files)


_HTTPS_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB — fits comfortably in LLM context


def _ensure_parent_dirs(
    client: globus_sdk.TransferClient, collection_id: str, dest_path: str
) -> None:
    """Create any missing directory segments up to dest_path's parent."""
    from pathlib import PurePosixPath

    parent = PurePosixPath(dest_path).parent
    if str(parent) == "/":
        return

    # Fast path: parent already exists (the common case).
    try:
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


def _get_https_auth_header(
    ctx: Context[GlobusContext], collection_id: str
) -> tuple[str, str]:
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
    return https_base_url, authorizer.get_authorization_header()


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
    Upload a file to a Globus collection via HTTPS.

    Most globus transfers require both a source and a destination collection. For small files,
     the LLM can upload directly to Globus without a source collection.

    Requires the collection to have HTTPS access enabled. Supports text ('utf-8') and
    binary ('base64') content up to 1 MiB. Parent directories are created automatically.
    Use `globus_transfer_submit_file_transfer_task` for files larger than 1 MiB.
    """
    log_tool_call(ctx, tool_name=globus_transfer_upload_file_via_https.__name__, service=_SERVICE)

    if encoding == "base64":
        try:
            content_bytes = base64.b64decode(content)
        except Exception as e:
            raise ToolError(f"Invalid base64 content: {e}") from e
    else:
        content_bytes = content.encode("utf-8")

    if len(content_bytes) > _HTTPS_MAX_BYTES:
        raise ToolError(
            f"Content size {len(content_bytes):,} bytes exceeds the 1 MiB limit."
            " Use `globus_transfer_submit_file_transfer_task` for larger files."
        )

    try:
        https_base_url, auth_header = _get_https_auth_header(ctx, collection_id)
    except ToolError as e:
        log_tool_error(
            ctx,
            tool_name=globus_transfer_upload_file_via_https.__name__,
            service=_SERVICE,
            error=e,
        )
        raise

    client = get_transfer_client(ctx)
    try:
        _ensure_parent_dirs(client, collection_id, dest_path)
    except globus_sdk.GlobusAPIError as e:
        log_tool_error(
            ctx,
            tool_name=globus_transfer_upload_file_via_https.__name__,
            service=_SERVICE,
            error=e,
        )
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
        log_tool_error(
            ctx,
            tool_name=globus_transfer_upload_file_via_https.__name__,
            service=_SERVICE,
            error=e,
        )
        raise ToolError(
            f"HTTPS upload failed ({e.response.status_code}): {e.response.text}"
        ) from e
    except httpx2.RequestError as e:
        log_tool_error(
            ctx,
            tool_name=globus_transfer_upload_file_via_https.__name__,
            service=_SERVICE,
            error=e,
        )
        raise ToolError(f"HTTPS request error: {e}") from e

    log_tool_result(
        ctx,
        tool_name=globus_transfer_upload_file_via_https.__name__,
        service=_SERVICE,
        result={"url": url, "size_bytes": len(content_bytes)},
    )
    return HttpsUploadResponse(url=url, path=dest_path)


def globus_transfer_download_file_via_https(
    collection_id: Annotated[str, Field(description="UUID of the Globus collection")],
    source_path: Annotated[
        str,
        Field(description="Path to the file on the collection (e.g. /folder/file.txt)"),
    ],
    *,
    ctx: Context[GlobusContext],
) -> HttpsDownloadResponse:
    """
    Download a file from a Globus collection via HTTPS.

    Most globus transfers require both a source and a destination collection. For small files,
     the LLM can download directly from Globus without a destination collection.

    Requires the collection to have HTTPS access enabled. Files up to 1 MiB are returned
    as UTF-8 text or base64-encoded binary. Use `globus_transfer_submit_file_transfer_task`
    to move files larger than 1 MiB between collections.
    """
    log_tool_call(
        ctx, tool_name=globus_transfer_download_file_via_https.__name__, service=_SERVICE
    )

    try:
        https_base_url, auth_header = _get_https_auth_header(ctx, collection_id)
    except ToolError as e:
        log_tool_error(
            ctx,
            tool_name=globus_transfer_download_file_via_https.__name__,
            service=_SERVICE,
            error=e,
        )
        raise

    url = https_base_url.rstrip("/") + "/" + source_path.lstrip("/")

    try:
        with httpx2.Client() as http_client:
            with http_client.stream("GET", url, headers={"Authorization": auth_header}) as response:
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > _HTTPS_MAX_BYTES:
                    raise ToolError(
                        f"File size {int(content_length):,} bytes exceeds the 1 MiB limit."
                        " Use `globus_transfer_submit_file_transfer_task` for larger files."
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > _HTTPS_MAX_BYTES:
                        raise ToolError(
                            "File exceeds the 1 MiB limit."
                            " Use `globus_transfer_submit_file_transfer_task` for larger files."
                        )
                    chunks.append(chunk)
                content_bytes = b"".join(chunks)
    except httpx2.HTTPStatusError as e:
        log_tool_error(
            ctx,
            tool_name=globus_transfer_download_file_via_https.__name__,
            service=_SERVICE,
            error=e,
        )
        raise ToolError(
            f"HTTPS download failed ({e.response.status_code}): {e.response.text}"
        ) from e
    except httpx2.RequestError as e:
        log_tool_error(
            ctx,
            tool_name=globus_transfer_download_file_via_https.__name__,
            service=_SERVICE,
            error=e,
        )
        raise ToolError(f"HTTPS request error: {e}") from e

    try:
        content_str = content_bytes.decode("utf-8")
        file_encoding: Literal["utf-8", "base64"] = "utf-8"
    except UnicodeDecodeError:
        content_str = base64.b64encode(content_bytes).decode("ascii")
        file_encoding = "base64"

    log_tool_result(
        ctx,
        tool_name=globus_transfer_download_file_via_https.__name__,
        service=_SERVICE,
        result={"url": url, "size_bytes": len(content_bytes), "encoding": file_encoding},
    )
    return HttpsDownloadResponse(
        content=content_str,
        encoding=file_encoding,
        size_bytes=len(content_bytes),
        url=url,
    )


TRANSFER_TOOLS_BY_CATEGORY: dict[ToolCategory, list[Callable[..., Any]]] = {
    ToolCategory.READ: [
        globus_transfer_search_collections,
        globus_transfer_list_collections,
        globus_transfer_get_task_status,
        globus_transfer_get_task_events,
        globus_transfer_list_directory_contents,
        globus_transfer_download_file_via_https,
    ],
    ToolCategory.OPERATE: [
        globus_transfer_submit_file_transfer_task,
        globus_transfer_upload_file_via_https,
    ],
    ToolCategory.ADMIN: [],
}
