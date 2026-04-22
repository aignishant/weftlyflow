"""Constants for the Brevo v3 REST integration node.

Reference: https://developers.brevo.com/reference/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.brevo.com"
API_VERSION_PREFIX: Final[str] = "/v3"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_SEND_EMAIL: Final[str] = "send_email"
OP_CREATE_CONTACT: Final[str] = "create_contact"
OP_UPDATE_CONTACT: Final[str] = "update_contact"
OP_GET_CONTACT: Final[str] = "get_contact"
OP_ADD_CONTACT_TO_LIST: Final[str] = "add_contact_to_list"
OP_GET_ACCOUNT: Final[str] = "get_account"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_SEND_EMAIL,
    OP_CREATE_CONTACT,
    OP_UPDATE_CONTACT,
    OP_GET_CONTACT,
    OP_ADD_CONTACT_TO_LIST,
    OP_GET_ACCOUNT,
)
