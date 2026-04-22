"""Constants for the Freshdesk v2 integration node.

Reference: https://developers.freshdesk.com/api/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_TICKETS: Final[str] = "list_tickets"
OP_GET_TICKET: Final[str] = "get_ticket"
OP_CREATE_TICKET: Final[str] = "create_ticket"
OP_UPDATE_TICKET: Final[str] = "update_ticket"
OP_LIST_CONTACTS: Final[str] = "list_contacts"
OP_CREATE_CONTACT: Final[str] = "create_contact"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_TICKETS,
    OP_GET_TICKET,
    OP_CREATE_TICKET,
    OP_UPDATE_TICKET,
    OP_LIST_CONTACTS,
    OP_CREATE_CONTACT,
)

DEFAULT_PER_PAGE: Final[int] = 30
MAX_PER_PAGE: Final[int] = 100

TICKET_PRIORITIES: Final[dict[str, int]] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "urgent": 4,
}

TICKET_STATUSES: Final[dict[str, int]] = {
    "open": 2,
    "pending": 3,
    "resolved": 4,
    "closed": 5,
}

TICKET_SOURCES: Final[dict[str, int]] = {
    "email": 1,
    "portal": 2,
    "phone": 3,
    "chat": 7,
    "feedback_widget": 9,
}

TICKET_UPDATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "subject",
        "description",
        "priority",
        "status",
        "source",
        "type",
        "tags",
        "group_id",
        "responder_id",
        "requester_id",
        "email",
        "custom_fields",
    },
)
