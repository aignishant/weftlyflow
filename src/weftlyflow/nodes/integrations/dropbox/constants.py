"""Constants for the Dropbox integration node.

Reference: https://www.dropbox.com/developers/documentation/http/documentation.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.dropboxapi.com"
CONTENT_BASE_URL: Final[str] = "https://content.dropboxapi.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_FOLDER: Final[str] = "list_folder"
OP_GET_METADATA: Final[str] = "get_metadata"
OP_CREATE_FOLDER: Final[str] = "create_folder"
OP_DELETE: Final[str] = "delete"
OP_MOVE: Final[str] = "move"
OP_COPY: Final[str] = "copy"
OP_SEARCH: Final[str] = "search"
OP_DOWNLOAD: Final[str] = "download"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_FOLDER,
    OP_GET_METADATA,
    OP_CREATE_FOLDER,
    OP_DELETE,
    OP_MOVE,
    OP_COPY,
    OP_SEARCH,
    OP_DOWNLOAD,
)

DEFAULT_SEARCH_LIMIT: Final[int] = 100
MAX_SEARCH_LIMIT: Final[int] = 1_000
