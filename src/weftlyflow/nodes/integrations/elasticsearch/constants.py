"""Constants for the Elasticsearch integration node.

Reference: https://www.elastic.co/guide/en/elasticsearch/reference/current/rest-apis.html.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_SEARCH: Final[str] = "search"
OP_INDEX: Final[str] = "index"
OP_GET: Final[str] = "get"
OP_UPDATE: Final[str] = "update"
OP_DELETE: Final[str] = "delete"
OP_BULK: Final[str] = "bulk"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_SEARCH,
    OP_INDEX,
    OP_GET,
    OP_UPDATE,
    OP_DELETE,
    OP_BULK,
)

DEFAULT_SEARCH_SIZE: Final[int] = 10
MAX_SEARCH_SIZE: Final[int] = 10_000
