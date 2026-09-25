from pydantic import BaseModel, Field

from globus_mcp.services.transfer.schemas.base import PaginationMixin


class TransferFile(BaseModel):
    name: str = Field(description="Name of the file")
    type: str = Field(description="The type of the entry: file, dir, chr, blk, pipe, or other. For symlinks the type reflects the target.")
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


class TransferFileList(PaginationMixin):
    data: list[TransferFile] = Field(description="Set of transfer file data")
