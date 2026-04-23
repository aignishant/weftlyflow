"""Constants for the Salesforce REST integration node.

Reference: https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_API_VERSION: Final[str] = "v58.0"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_RECORDS: Final[str] = "list_records"
OP_GET_RECORD: Final[str] = "get_record"
OP_CREATE_RECORD: Final[str] = "create_record"
OP_UPDATE_RECORD: Final[str] = "update_record"
OP_DELETE_RECORD: Final[str] = "delete_record"
OP_QUERY: Final[str] = "query"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_RECORDS,
    OP_GET_RECORD,
    OP_CREATE_RECORD,
    OP_UPDATE_RECORD,
    OP_DELETE_RECORD,
    OP_QUERY,
)

DEFAULT_LIST_LIMIT: Final[int] = 200
MAX_LIST_LIMIT: Final[int] = 2_000
