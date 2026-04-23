"""Constants for the Cloudinary integration node.

Reference: https://cloudinary.com/documentation/image_upload_api_reference.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0

OP_UPLOAD: Final[str] = "upload"
OP_DESTROY: Final[str] = "destroy"
OP_LIST_RESOURCES: Final[str] = "list_resources"
OP_GET_RESOURCE: Final[str] = "get_resource"

RESOURCE_IMAGE: Final[str] = "image"
RESOURCE_VIDEO: Final[str] = "video"
RESOURCE_RAW: Final[str] = "raw"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_UPLOAD,
    OP_DESTROY,
    OP_LIST_RESOURCES,
    OP_GET_RESOURCE,
)

SUPPORTED_RESOURCE_TYPES: Final[tuple[str, ...]] = (
    RESOURCE_IMAGE,
    RESOURCE_VIDEO,
    RESOURCE_RAW,
)

SIGNED_OPERATIONS: Final[frozenset[str]] = frozenset({OP_UPLOAD, OP_DESTROY})
