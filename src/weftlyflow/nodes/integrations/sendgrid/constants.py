"""Constants for the SendGrid integration node.

Reference: https://docs.sendgrid.com/api-reference/mail-send/mail-send.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.sendgrid.com"
MAIL_SEND_ENDPOINT: Final[str] = "/v3/mail/send"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_SEND_EMAIL: Final[str] = "send_email"
SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (OP_SEND_EMAIL,)

CONTENT_TYPE_TEXT: Final[str] = "text/plain"
CONTENT_TYPE_HTML: Final[str] = "text/html"
