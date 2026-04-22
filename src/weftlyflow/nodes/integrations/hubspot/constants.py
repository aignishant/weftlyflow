"""Constants for the HubSpot CRM v3 integration node.

Reference: https://developers.hubspot.com/docs/api/crm/contacts.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.hubapi.com"
API_VERSION_PREFIX: Final[str] = "/crm/v3"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_CREATE_CONTACT: Final[str] = "create_contact"
OP_UPDATE_CONTACT: Final[str] = "update_contact"
OP_GET_CONTACT: Final[str] = "get_contact"
OP_DELETE_CONTACT: Final[str] = "delete_contact"
OP_SEARCH_CONTACTS: Final[str] = "search_contacts"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_CREATE_CONTACT,
    OP_UPDATE_CONTACT,
    OP_GET_CONTACT,
    OP_DELETE_CONTACT,
    OP_SEARCH_CONTACTS,
)

DEFAULT_SEARCH_LIMIT: Final[int] = 10
MAX_SEARCH_LIMIT: Final[int] = 100
