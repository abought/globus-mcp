from collections.abc import Callable
from http import HTTPStatus
from typing import Annotated, Any, Literal

import globus_sdk
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from globus_mcp.core.audit import log_tool_call, log_tool_error, log_tool_result
from globus_mcp.core.context import GlobusContext
from globus_mcp.services.transfer.client import get_transfer_client
from globus_mcp.services.transfer.schemas import (
    TransferEvent,
    TransferEventList,
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
    ] = "checksum",
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
        skip_source_errors=skip_source_errors,  # real transfers may have partial failures

        # Hardcoded policies for LLM usage: make actions and failures obvious
        encrypt_data=True,
        fail_on_quota_errors=True,  # LLM can't intervene to fix out of band
        delete_destination_extra=False,  # don't expose to LLM- too much side effect risk
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

    Use this to check whether a transfer has completed, and to monitor byte and file counts
        during an in-progress transfer.
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
    Get details of progress for a Globus Transfer Task, such as faults and errors.

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
