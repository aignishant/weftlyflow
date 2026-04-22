"""Constants for the Zoho CRM v6 integration node.

Reference: https://www.zoho.com/crm/developer/docs/api/v6/.
"""

from __future__ import annotations

from typing import Final

API_VERSION_PREFIX: Final[str] = "/crm/v6"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_RECORDS: Final[str] = "list_records"
OP_GET_RECORD: Final[str] = "get_record"
OP_CREATE_RECORD: Final[str] = "create_record"
OP_UPDATE_RECORD: Final[str] = "update_record"
OP_DELETE_RECORD: Final[str] = "delete_record"
OP_SEARCH_RECORDS: Final[str] = "search_records"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_RECORDS,
    OP_GET_RECORD,
    OP_CREATE_RECORD,
    OP_UPDATE_RECORD,
    OP_DELETE_RECORD,
    OP_SEARCH_RECORDS,
)

DEFAULT_PER_PAGE: Final[int] = 50
MAX_PER_PAGE: Final[int] = 200

SEARCH_CRITERIA_KEYS: Final[frozenset[str]] = frozenset(
    {"criteria", "email", "phone", "word"},
)
