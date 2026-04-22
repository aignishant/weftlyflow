"""Constants for the Pushover integration node.

Reference: https://pushover.net/api.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.pushover.net/1"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_SEND_NOTIFICATION: Final[str] = "send_notification"
OP_SEND_GLANCE: Final[str] = "send_glance"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_SEND_NOTIFICATION,
    OP_SEND_GLANCE,
)

MIN_PRIORITY: Final[int] = -2
MAX_PRIORITY: Final[int] = 2
EMERGENCY_PRIORITY: Final[int] = 2
MIN_RETRY_SECONDS: Final[int] = 30
MAX_EXPIRE_SECONDS: Final[int] = 10_800  # 3 hours, per Pushover docs.

MESSAGE_MAX_LENGTH: Final[int] = 1024
TITLE_MAX_LENGTH: Final[int] = 250
URL_MAX_LENGTH: Final[int] = 512
URL_TITLE_MAX_LENGTH: Final[int] = 100

GLANCE_TEXT_MAX_LENGTH: Final[int] = 100
GLANCE_SUBTEXT_MAX_LENGTH: Final[int] = 100
