"""Constants for the Intercom REST integration node.

Reference: https://developers.intercom.com/docs/references/rest-api/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.intercom.io"
DEFAULT_VERSION: Final[str] = "2.11"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_CREATE_CONTACT: Final[str] = "create_contact"
OP_UPDATE_CONTACT: Final[str] = "update_contact"
OP_GET_CONTACT: Final[str] = "get_contact"
OP_SEARCH_CONTACTS: Final[str] = "search_contacts"
OP_CREATE_CONVERSATION: Final[str] = "create_conversation"
OP_REPLY_CONVERSATION: Final[str] = "reply_conversation"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_CREATE_CONTACT,
    OP_UPDATE_CONTACT,
    OP_GET_CONTACT,
    OP_SEARCH_CONTACTS,
    OP_CREATE_CONVERSATION,
    OP_REPLY_CONVERSATION,
)

DEFAULT_SEARCH_LIMIT: Final[int] = 25
MAX_SEARCH_LIMIT: Final[int] = 150
