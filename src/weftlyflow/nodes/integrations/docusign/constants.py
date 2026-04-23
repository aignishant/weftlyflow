"""Constants for the DocuSign eSignature integration node.

Reference: https://developers.docusign.com/docs/esign-rest-api/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_ENVELOPES: Final[str] = "list_envelopes"
OP_GET_ENVELOPE: Final[str] = "get_envelope"
OP_CREATE_ENVELOPE: Final[str] = "create_envelope"
OP_LIST_TEMPLATES: Final[str] = "list_templates"

STATUS_SENT: Final[str] = "sent"
STATUS_CREATED: Final[str] = "created"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_ENVELOPES,
    OP_GET_ENVELOPE,
    OP_CREATE_ENVELOPE,
    OP_LIST_TEMPLATES,
)
