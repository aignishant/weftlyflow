"""Constants for the Contentful integration node.

Reference: https://www.contentful.com/developers/docs/references/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
DEFAULT_ENVIRONMENT: Final[str] = "master"
MANAGEMENT_HOST: Final[str] = "https://api.contentful.com"
DELIVERY_HOST: Final[str] = "https://cdn.contentful.com"
VERSION_HEADER: Final[str] = "X-Contentful-Version"
CONTENT_TYPE_HEADER_VALUE: Final[str] = "application/vnd.contentful.management.v1+json"

OP_GET_ENTRY: Final[str] = "get_entry"
OP_LIST_ENTRIES: Final[str] = "list_entries"
OP_CREATE_ENTRY: Final[str] = "create_entry"
OP_UPDATE_ENTRY: Final[str] = "update_entry"
OP_PUBLISH_ENTRY: Final[str] = "publish_entry"
OP_DELETE_ENTRY: Final[str] = "delete_entry"
OP_GET_ASSET: Final[str] = "get_asset"

# Ops hitting the Delivery API (cdn.contentful.com).
DELIVERY_OPERATIONS: Final[frozenset[str]] = frozenset(
    {OP_LIST_ENTRIES, OP_GET_ENTRY, OP_GET_ASSET},
)

# Ops that must carry ``X-Contentful-Version`` on the request.
VERSIONED_WRITE_OPERATIONS: Final[frozenset[str]] = frozenset(
    {OP_UPDATE_ENTRY, OP_PUBLISH_ENTRY, OP_DELETE_ENTRY},
)

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GET_ENTRY,
    OP_LIST_ENTRIES,
    OP_CREATE_ENTRY,
    OP_UPDATE_ENTRY,
    OP_PUBLISH_ENTRY,
    OP_DELETE_ENTRY,
    OP_GET_ASSET,
)
