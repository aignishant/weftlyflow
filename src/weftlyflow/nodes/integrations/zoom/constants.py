"""Constants for the Zoom Meetings integration node.

Reference: https://developers.zoom.us/docs/api/meetings/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.zoom.us/v2"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_MEETINGS: Final[str] = "list_meetings"
OP_GET_MEETING: Final[str] = "get_meeting"
OP_CREATE_MEETING: Final[str] = "create_meeting"
OP_UPDATE_MEETING: Final[str] = "update_meeting"
OP_DELETE_MEETING: Final[str] = "delete_meeting"
OP_LIST_PAST_PARTICIPANTS: Final[str] = "list_past_participants"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_MEETINGS,
    OP_GET_MEETING,
    OP_CREATE_MEETING,
    OP_UPDATE_MEETING,
    OP_DELETE_MEETING,
    OP_LIST_PAST_PARTICIPANTS,
)

DEFAULT_PAGE_SIZE: Final[int] = 30
MAX_PAGE_SIZE: Final[int] = 300

MEETING_TYPE_INSTANT: Final[int] = 1
MEETING_TYPE_SCHEDULED: Final[int] = 2
MEETING_TYPE_RECURRING_NO_FIXED: Final[int] = 3
MEETING_TYPE_RECURRING_FIXED: Final[int] = 8

VALID_MEETING_TYPES: Final[frozenset[int]] = frozenset(
    {
        MEETING_TYPE_INSTANT,
        MEETING_TYPE_SCHEDULED,
        MEETING_TYPE_RECURRING_NO_FIXED,
        MEETING_TYPE_RECURRING_FIXED,
    },
)

LIST_TYPES: Final[frozenset[str]] = frozenset(
    {"scheduled", "live", "upcoming", "upcoming_meetings", "previous_meetings"},
)
