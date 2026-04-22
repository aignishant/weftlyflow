"""Constants for the Twilio Programmable Messaging integration node.

Reference: https://www.twilio.com/docs/messaging/api.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.twilio.com"
API_VERSION_PREFIX: Final[str] = "/2010-04-01"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_SEND_SMS: Final[str] = "send_sms"
OP_GET_MESSAGE: Final[str] = "get_message"
OP_LIST_MESSAGES: Final[str] = "list_messages"
OP_DELETE_MESSAGE: Final[str] = "delete_message"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_SEND_SMS,
    OP_GET_MESSAGE,
    OP_LIST_MESSAGES,
    OP_DELETE_MESSAGE,
)

DEFAULT_LIST_LIMIT: Final[int] = 20
MAX_LIST_LIMIT: Final[int] = 1000
