"""Constants for the NetSuite integration node.

Reference: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/
section_1559132836.html (SuiteTalk REST Web Services).
"""

from __future__ import annotations

from typing import Final

REST_PATH: Final[str] = "/services/rest"
SUITEQL_PATH: Final[str] = f"{REST_PATH}/query/v1/suiteql"
RECORD_PATH: Final[str] = f"{REST_PATH}/record/v1"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0
SUITEQL_HEADER: Final[str] = "Prefer"
SUITEQL_HEADER_VALUE: Final[str] = "transient"

OP_SUITEQL_QUERY: Final[str] = "suiteql_query"
OP_RECORD_GET: Final[str] = "record_get"
OP_RECORD_CREATE: Final[str] = "record_create"
OP_RECORD_DELETE: Final[str] = "record_delete"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_SUITEQL_QUERY,
    OP_RECORD_GET,
    OP_RECORD_CREATE,
    OP_RECORD_DELETE,
)
