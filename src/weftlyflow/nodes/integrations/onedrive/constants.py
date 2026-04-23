"""Constants for the OneDrive integration node.

Reference: https://learn.microsoft.com/en-us/graph/api/resources/onedrive.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0
GRAPH_API_BASE: Final[str] = "https://graph.microsoft.com/v1.0"
DRIVE_ROOT_PREFIX: Final[str] = "/me/drive"

SIMPLE_UPLOAD_LIMIT_BYTES: Final[int] = 4 * 1024 * 1024  # 4 MiB
DEFAULT_UPLOAD_CHUNK_BYTES: Final[int] = 10 * 320 * 1024  # ~3.2 MiB (multiple of 320 KiB)

OP_LIST_CHILDREN: Final[str] = "list_children"
OP_GET_ITEM: Final[str] = "get_item"
OP_UPLOAD_SMALL: Final[str] = "upload_small"
OP_UPLOAD_LARGE: Final[str] = "upload_large"
OP_DOWNLOAD_ITEM: Final[str] = "download_item"
OP_DELETE_ITEM: Final[str] = "delete_item"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_CHILDREN,
    OP_GET_ITEM,
    OP_UPLOAD_SMALL,
    OP_UPLOAD_LARGE,
    OP_DOWNLOAD_ITEM,
    OP_DELETE_ITEM,
)
