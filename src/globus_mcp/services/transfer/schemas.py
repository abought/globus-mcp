from typing import Literal

from pydantic import BaseModel, Field


class TransferEndpoint(BaseModel):
    endpoint_id: str = Field(description="ID of the endpoint")
    display_name: str = Field(description="Friendly name for the endpoint")
    owner_id: str = Field(description="ID of the endpoint owner")
    owner_string: str = Field(description="Identity name of the endpoint owner")
    type: str = Field(description="The type of endpoint")
    description: str | None = Field(default=None, description="A description of the endpoint")


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


class TransferSubmitResponse(BaseModel):
    task_id: str = Field(description="ID of the transfer task")


class TransferFile(BaseModel):
    name: str = Field(description="Name of the file")
    type: str = Field(description="The type of the entry: dir, file, or invalid_symlink.")
    link_target: str | None = Field(
        default=None,
        description=(
            "If this entry is a symlink (valid or invalid), this is the path of its target,"
            " which may be an absolute or relative path. If this entry is not a symlink, this"
            " field is null."
        ),
    )
    user: str | None = Field(
        default=None,
        description="The user owning the file or directory, if applicable.",
    )
    group: str | None = Field(
        default=None,
        description="The group owning the file or directory, if applicable.",
    )
    permissions: str = Field(description="The unix permissions, as an octal mode string.")
    size: int = Field(description="The file size in bytes.")
    last_modified: str = Field(
        description=(
            "The date and time the file or directory was last modified, in modified ISO 8601"
            " format: YYYY-MM-DD HH:MM:SS+00:00, i.e. using space instead of 'T' to separate"
            " date and time. Always in UTC, indicated explicitly with a trailing '+00:00'"
            " timezone."
        )
    )


###
# Pagination
###


class TransferList(BaseModel):
    offset: int = Field(description="Zero based offset into the result set.")
    limit: int = Field(description="Maximum number of results to return.")


class TransferCollectionList(TransferList):
    has_next_page: bool = Field(
        description="Indicates whether making a query at the next offset would yield more results",
    )
    data: list[TransferEndpoint] = Field(description="Set of transfer endpoints")


class TransferEventList(TransferList):
    data: list[TransferEvent] = Field(description="Set of transfer task events")


class TransferFileList(TransferList):
    data: list[TransferFile] = Field(description="Set of transfer file data")


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


class HttpsUploadResponse(BaseModel):
    url: str = Field(description="URL of the file on the collection")
    path: str = Field(description="Path of the file on the collection")


class HttpsDownloadResponse(BaseModel):
    content: str = Field(
        description="File content, encoded as specified by the 'encoding' field"
    )
    encoding: Literal["utf-8", "base64"] = Field(
        description="Content encoding: 'utf-8' for text files, 'base64' for binary files"
    )
    size_bytes: int = Field(description="Size of the file content in bytes")
    url: str = Field(description="URL the file was downloaded from")
