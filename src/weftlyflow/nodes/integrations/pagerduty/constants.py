"""Constants for the PagerDuty REST v2 integration node.

Reference: https://developer.pagerduty.com/api-reference/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.pagerduty.com"
ACCEPT_HEADER: Final[str] = "application/vnd.pagerduty+json;version=2"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_INCIDENTS: Final[str] = "list_incidents"
OP_GET_INCIDENT: Final[str] = "get_incident"
OP_CREATE_INCIDENT: Final[str] = "create_incident"
OP_UPDATE_INCIDENT: Final[str] = "update_incident"
OP_ADD_NOTE: Final[str] = "add_note"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_INCIDENTS,
    OP_GET_INCIDENT,
    OP_CREATE_INCIDENT,
    OP_UPDATE_INCIDENT,
    OP_ADD_NOTE,
)

DEFAULT_LIST_LIMIT: Final[int] = 25
MAX_LIST_LIMIT: Final[int] = 100

INCIDENT_STATUSES: Final[frozenset[str]] = frozenset(
    {"triggered", "acknowledged", "resolved"},
)
INCIDENT_URGENCIES: Final[frozenset[str]] = frozenset({"high", "low"})
