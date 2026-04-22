"""Constants for the Algolia Search v1 integration node.

Reference: https://www.algolia.com/doc/rest-api/search/.
"""

from __future__ import annotations

from typing import Final

API_VERSION_PREFIX: Final[str] = "/1"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_SEARCH: Final[str] = "search"
OP_ADD_OBJECT: Final[str] = "add_object"
OP_UPDATE_OBJECT: Final[str] = "update_object"
OP_GET_OBJECT: Final[str] = "get_object"
OP_DELETE_OBJECT: Final[str] = "delete_object"
OP_LIST_INDICES: Final[str] = "list_indices"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_SEARCH,
    OP_ADD_OBJECT,
    OP_UPDATE_OBJECT,
    OP_GET_OBJECT,
    OP_DELETE_OBJECT,
    OP_LIST_INDICES,
)

DEFAULT_HITS_PER_PAGE: Final[int] = 20
MAX_HITS_PER_PAGE: Final[int] = 1000


def search_host_for(application_id: str) -> str:
    """Return the DSN host used for read operations."""
    return f"{application_id}-dsn.algolia.net"


def write_host_for(application_id: str) -> str:
    """Return the write host used for indexing operations."""
    return f"{application_id}.algolia.net"
