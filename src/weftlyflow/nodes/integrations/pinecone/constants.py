"""Constants for the Pinecone integration node.

Reference: https://docs.pinecone.io/reference/api/introduction.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
CONTROL_PLANE_HOST: Final[str] = "https://api.pinecone.io"

OP_LIST_INDEXES: Final[str] = "list_indexes"
OP_DESCRIBE_INDEX: Final[str] = "describe_index"
OP_QUERY_VECTORS: Final[str] = "query_vectors"
OP_UPSERT_VECTORS: Final[str] = "upsert_vectors"
OP_FETCH_VECTORS: Final[str] = "fetch_vectors"
OP_DELETE_VECTORS: Final[str] = "delete_vectors"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_INDEXES,
    OP_DESCRIBE_INDEX,
    OP_QUERY_VECTORS,
    OP_UPSERT_VECTORS,
    OP_FETCH_VECTORS,
    OP_DELETE_VECTORS,
)

CONTROL_PLANE_OPERATIONS: Final[frozenset[str]] = frozenset(
    {OP_LIST_INDEXES, OP_DESCRIBE_INDEX},
)
DATA_PLANE_OPERATIONS: Final[frozenset[str]] = frozenset(
    {OP_QUERY_VECTORS, OP_UPSERT_VECTORS, OP_FETCH_VECTORS, OP_DELETE_VECTORS},
)
