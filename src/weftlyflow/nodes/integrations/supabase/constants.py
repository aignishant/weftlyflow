"""Constants for the Supabase PostgREST integration node.

Reference: https://supabase.com/docs/guides/database/api and the
underlying PostgREST spec at https://postgrest.org/en/stable/.
"""

from __future__ import annotations

from typing import Final

REST_VERSION_PREFIX: Final[str] = "/rest/v1"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_SELECT: Final[str] = "select"
OP_INSERT: Final[str] = "insert"
OP_UPDATE: Final[str] = "update"
OP_DELETE: Final[str] = "delete"
OP_UPSERT: Final[str] = "upsert"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_SELECT,
    OP_INSERT,
    OP_UPDATE,
    OP_DELETE,
    OP_UPSERT,
)

DEFAULT_LIMIT: Final[int] = 100
MAX_LIMIT: Final[int] = 1000

RETURN_REPRESENTATION: Final[str] = "return=representation"
RESOLUTION_MERGE: Final[str] = "resolution=merge-duplicates"
