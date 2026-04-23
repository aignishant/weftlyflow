"""Constants for the Google Drive integration node.

Reference: https://developers.google.com/drive/api/reference/rest/v3.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0
DRIVE_API_BASE: Final[str] = "https://www.googleapis.com"
DRIVE_API_PREFIX: Final[str] = "/drive/v3"
DRIVE_UPLOAD_PREFIX: Final[str] = "/upload/drive/v3"
MULTIPART_BOUNDARY: Final[str] = "weftlyflow-drive-boundary"

OP_LIST_FILES: Final[str] = "list_files"
OP_GET_FILE: Final[str] = "get_file"
OP_CREATE_FOLDER: Final[str] = "create_folder"
OP_UPLOAD_FILE: Final[str] = "upload_file"
OP_DOWNLOAD_FILE: Final[str] = "download_file"
OP_DELETE_FILE: Final[str] = "delete_file"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_FILES,
    OP_GET_FILE,
    OP_CREATE_FOLDER,
    OP_UPLOAD_FILE,
    OP_DOWNLOAD_FILE,
    OP_DELETE_FILE,
)
