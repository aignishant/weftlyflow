"""Constants for the Klaviyo integration node.

Reference: https://developers.klaviyo.com/en/reference/api_overview.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://a.klaviyo.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 15.0

OP_CREATE_EVENT: Final[str] = "create_event"
OP_CREATE_PROFILE: Final[str] = "create_profile"
OP_GET_PROFILE: Final[str] = "get_profile"
OP_ADD_PROFILE_TO_LIST: Final[str] = "add_profile_to_list"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_CREATE_EVENT,
    OP_CREATE_PROFILE,
    OP_GET_PROFILE,
    OP_ADD_PROFILE_TO_LIST,
)
