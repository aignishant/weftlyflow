"""Constants for the GA4 Measurement Protocol node.

Reference: https://developers.google.com/analytics/devguides/collection/protocol/ga4/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://www.google-analytics.com"
COLLECT_PATH: Final[str] = "/mp/collect"
DEBUG_COLLECT_PATH: Final[str] = "/debug/mp/collect"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 15.0

OP_TRACK_EVENT: Final[str] = "track_event"
OP_TRACK_EVENTS: Final[str] = "track_events"
OP_VALIDATE_EVENT: Final[str] = "validate_event"
OP_USER_PROPERTIES: Final[str] = "user_properties"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_TRACK_EVENT,
    OP_TRACK_EVENTS,
    OP_VALIDATE_EVENT,
    OP_USER_PROPERTIES,
)
