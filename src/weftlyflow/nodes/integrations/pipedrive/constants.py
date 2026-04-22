"""Constants for the Pipedrive v1 integration node.

Reference: https://developers.pipedrive.com/docs/api/v1/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_DEALS: Final[str] = "list_deals"
OP_GET_DEAL: Final[str] = "get_deal"
OP_CREATE_DEAL: Final[str] = "create_deal"
OP_UPDATE_DEAL: Final[str] = "update_deal"
OP_CREATE_PERSON: Final[str] = "create_person"
OP_CREATE_ACTIVITY: Final[str] = "create_activity"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_DEALS,
    OP_GET_DEAL,
    OP_CREATE_DEAL,
    OP_UPDATE_DEAL,
    OP_CREATE_PERSON,
    OP_CREATE_ACTIVITY,
)

DEFAULT_LIST_LIMIT: Final[int] = 100
MAX_LIST_LIMIT: Final[int] = 500

DEAL_STATUSES: Final[frozenset[str]] = frozenset(
    {"open", "won", "lost", "deleted", "all_not_deleted"},
)
