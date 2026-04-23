"""Constants for the Azure Blob Storage integration node.

Reference: https://learn.microsoft.com/rest/api/storageservices/blob-service-rest-api.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0

OP_LIST_CONTAINERS: Final[str] = "list_containers"
OP_LIST_BLOBS: Final[str] = "list_blobs"
OP_GET_BLOB: Final[str] = "get_blob"
OP_PUT_BLOB: Final[str] = "put_blob"
OP_DELETE_BLOB: Final[str] = "delete_blob"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_CONTAINERS,
    OP_LIST_BLOBS,
    OP_GET_BLOB,
    OP_PUT_BLOB,
    OP_DELETE_BLOB,
)

BLOB_TYPE_BLOCK: Final[str] = "BlockBlob"
