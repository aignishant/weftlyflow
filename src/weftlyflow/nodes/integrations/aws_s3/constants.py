"""Constants for the AWS S3 integration node.

Reference: https://docs.aws.amazon.com/AmazonS3/latest/API/Welcome.html.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0

OP_LIST_BUCKETS: Final[str] = "list_buckets"
OP_LIST_OBJECTS: Final[str] = "list_objects"
OP_HEAD_OBJECT: Final[str] = "head_object"
OP_GET_OBJECT: Final[str] = "get_object"
OP_DELETE_OBJECT: Final[str] = "delete_object"
OP_COPY_OBJECT: Final[str] = "copy_object"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_BUCKETS,
    OP_LIST_OBJECTS,
    OP_HEAD_OBJECT,
    OP_GET_OBJECT,
    OP_DELETE_OBJECT,
    OP_COPY_OBJECT,
)

DEFAULT_MAX_KEYS: Final[int] = 1_000
MAX_MAX_KEYS: Final[int] = 1_000
