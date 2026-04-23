"""Constants for the Facebook Graph integration node.

Reference: https://developers.facebook.com/docs/graph-api.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
DEFAULT_API_VERSION: Final[str] = "v21.0"

OP_GET_ME: Final[str] = "get_me"
OP_GET_NODE: Final[str] = "get_node"
OP_LIST_EDGE: Final[str] = "list_edge"
OP_CREATE_EDGE: Final[str] = "create_edge"
OP_DELETE_NODE: Final[str] = "delete_node"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GET_ME,
    OP_GET_NODE,
    OP_LIST_EDGE,
    OP_CREATE_EDGE,
    OP_DELETE_NODE,
)
