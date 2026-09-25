from collections.abc import Callable
from typing import Any

from globus_mcp.core.categories import ToolCategory
from globus_mcp.services.transfer.tools.collections import (
    globus_transfer_list_collections,
    globus_transfer_search_collections,
)
from globus_mcp.services.transfer.tools.fs import globus_transfer_list_directory_contents
# from globus_mcp.services.transfer.tools.https import (
#     globus_transfer_direct_read_content,
#     globus_transfer_download_file_via_https,
#     globus_transfer_upload_content_via_https,
#     globus_transfer_upload_file_via_https,
# )
from globus_mcp.services.transfer.tools.tasks import (
    globus_transfer_get_task_events,
    globus_transfer_get_task_status,
    globus_transfer_submit_file_transfer_task,
)

TRANSFER_TOOLS_BY_CATEGORY: dict[ToolCategory, list[Callable[..., Any]]] = {
    ToolCategory.READ: [
        globus_transfer_search_collections,
        globus_transfer_list_collections,
        globus_transfer_get_task_status,
        globus_transfer_get_task_events,
        globus_transfer_list_directory_contents,
        #globus_transfer_direct_read_content,
    ],
    ToolCategory.OPERATE: [
        globus_transfer_submit_file_transfer_task,
        #globus_transfer_upload_content_via_https,
    ],
    ToolCategory.ADMIN: [],
}

# Registered only when FILESYSTEM_ROOT is configured at startup.
TRANSFER_FILE_TOOLS_BY_CATEGORY: dict[ToolCategory, list[Callable[..., Any]]] = {
    ToolCategory.READ: [
        #globus_transfer_download_file_via_https,
    ],
    ToolCategory.OPERATE: [
        #globus_transfer_upload_file_via_https,
    ],
    ToolCategory.ADMIN: [],
}
