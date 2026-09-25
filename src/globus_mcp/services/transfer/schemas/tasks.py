from pydantic import BaseModel, Field

from globus_mcp.services.transfer.schemas.base import PaginationMixin


class TransferItem(BaseModel):
    source_path: str = Field(description="Path to the source file or directory")
    destination_path: str = Field(description="Path to the destination file or directory")
    recursive: bool | None = Field(
        default=None,
        description=(
            "Set to True when transferring a directory; omit or leave None for individual files."
            " (SDK default: None, treated as non-recursive by the Transfer service.)"
        ),
    )


class TransferSubmitResponse(BaseModel):
    task_id: str = Field(description="ID of the transfer task")


class TransferTask(BaseModel):
    task_id: str = Field(description="ID of the task")
    status: str = Field(description="Task status: ACTIVE, SUCCEEDED, FAILED, or INACTIVE")
    label: str | None = Field(default=None, description="Human-readable label for the task")
    bytes_transferred: int | None = Field(default=None, description="Bytes transferred so far")
    files_transferred: int | None = Field(default=None, description="Files transferred so far")
    files_skipped: int | None = Field(
        default=None, description="Files skipped (e.g. due to sync_level)"
    )
    deadline: str | None = Field(default=None, description="Deadline for the task, if set")
    completion_time: str | None = Field(
        default=None, description="Time the task completed, if finished"
    )


class TransferEvent(BaseModel):
    code: str = Field(description="A code indicating the type of the event.")
    is_error: bool = Field(description="true if event is an error event")
    description: str = Field(description="A description of the event.")
    details: str = Field(description="Type specific details about the event.")
    time: str = Field(
        description=(
            "The date and time the event occurred, in ISO 8601 format"
            " (YYYY-MM-DD HH:MM:SS) and UTC."
        )
    )


class TransferEventList(PaginationMixin):
    data: list[TransferEvent] = Field(description="Set of transfer task events")
