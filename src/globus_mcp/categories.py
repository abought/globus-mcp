from enum import StrEnum


class ToolCategory(StrEnum):
    READ = "read"
    OPERATE = "operate"
    ADMIN = "admin"


DEFAULT_CATEGORIES: tuple[ToolCategory, ...] = (ToolCategory.READ,)
