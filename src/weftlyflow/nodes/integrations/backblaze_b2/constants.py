"""Constants for the Backblaze B2 integration node.

Reference: https://www.backblaze.com/apidocs.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0

OP_LIST_BUCKETS: Final[str] = "list_buckets"
OP_LIST_FILE_NAMES: Final[str] = "list_file_names"
OP_GET_UPLOAD_URL: Final[str] = "get_upload_url"
OP_DELETE_FILE_VERSION: Final[str] = "delete_file_version"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_BUCKETS,
    OP_LIST_FILE_NAMES,
    OP_GET_UPLOAD_URL,
    OP_DELETE_FILE_VERSION,
)

DEFAULT_MAX_FILE_COUNT: Final[int] = 100
MAX_FILE_COUNT: Final[int] = 10_000
