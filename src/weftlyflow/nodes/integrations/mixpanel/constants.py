"""Constants for the Mixpanel integration node.

Reference: https://developer.mixpanel.com/reference/overview.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.mixpanel.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 15.0

OP_TRACK_EVENT: Final[str] = "track_event"
OP_ENGAGE_USER: Final[str] = "engage_user"
OP_UPDATE_GROUP: Final[str] = "update_group"
OP_IMPORT_EVENTS: Final[str] = "import_events"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_TRACK_EVENT,
    OP_ENGAGE_USER,
    OP_UPDATE_GROUP,
    OP_IMPORT_EVENTS,
)
