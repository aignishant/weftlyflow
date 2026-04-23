"""Constants for the Snowflake SQL API integration node.

Reference: https://docs.snowflake.com/en/developer-guide/sql-api/index.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0
TOKEN_TYPE_HEADER: Final[str] = "X-Snowflake-Authorization-Token-Type"

OP_EXECUTE: Final[str] = "execute"
OP_GET_STATUS: Final[str] = "get_status"
OP_CANCEL: Final[str] = "cancel"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (OP_EXECUTE, OP_GET_STATUS, OP_CANCEL)

DEFAULT_FETCH_ROWS: Final[int] = 10_000
MAX_FETCH_ROWS: Final[int] = 100_000
