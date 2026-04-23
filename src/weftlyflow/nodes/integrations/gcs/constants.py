"""Constants for the Google Cloud Storage integration node.

Reference: https://cloud.google.com/storage/docs/json_api.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0

API_HOST: Final[str] = "https://storage.googleapis.com"

OP_LIST_BUCKETS: Final[str] = "list_buckets"
OP_LIST_OBJECTS: Final[str] = "list_objects"
OP_GET_OBJECT: Final[str] = "get_object"
OP_DELETE_OBJECT: Final[str] = "delete_object"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_BUCKETS,
    OP_LIST_OBJECTS,
    OP_GET_OBJECT,
    OP_DELETE_OBJECT,
)
