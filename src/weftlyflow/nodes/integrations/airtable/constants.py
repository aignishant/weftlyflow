"""Constants for the Airtable integration node.

Reference: https://airtable.com/developers/web/api/introduction.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.airtable.com"
API_VERSION_PREFIX: Final[str] = "/v0"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_RECORDS: Final[str] = "list_records"
OP_GET_RECORD: Final[str] = "get_record"
OP_CREATE_RECORDS: Final[str] = "create_records"
OP_UPDATE_RECORD: Final[str] = "update_record"
OP_DELETE_RECORD: Final[str] = "delete_record"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_RECORDS,
    OP_GET_RECORD,
    OP_CREATE_RECORDS,
    OP_UPDATE_RECORD,
    OP_DELETE_RECORD,
)

DEFAULT_PAGE_SIZE: Final[int] = 100
MAX_PAGE_SIZE: Final[int] = 100
MAX_RECORDS_PER_CREATE: Final[int] = 10
