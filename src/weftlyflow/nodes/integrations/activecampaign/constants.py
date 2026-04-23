"""Constants for the ActiveCampaign integration node.

Reference: https://developers.activecampaign.com/reference/overview.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
API_TOKEN_HEADER: Final[str] = "Api-Token"

OP_LIST_CONTACTS: Final[str] = "list_contacts"
OP_GET_CONTACT: Final[str] = "get_contact"
OP_CREATE_CONTACT: Final[str] = "create_contact"
OP_UPDATE_CONTACT: Final[str] = "update_contact"
OP_DELETE_CONTACT: Final[str] = "delete_contact"
OP_ADD_CONTACT_TO_LIST: Final[str] = "add_contact_to_list"
OP_ADD_TAG_TO_CONTACT: Final[str] = "add_tag_to_contact"
OP_LIST_TAGS: Final[str] = "list_tags"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_CONTACTS,
    OP_GET_CONTACT,
    OP_CREATE_CONTACT,
    OP_UPDATE_CONTACT,
    OP_DELETE_CONTACT,
    OP_ADD_CONTACT_TO_LIST,
    OP_ADD_TAG_TO_CONTACT,
    OP_LIST_TAGS,
)

DEFAULT_PAGE_SIZE: Final[int] = 20
MAX_PAGE_SIZE: Final[int] = 100

VALID_LIST_STATUSES: Final[frozenset[int]] = frozenset({1, 2})
