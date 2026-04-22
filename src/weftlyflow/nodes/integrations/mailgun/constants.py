"""Constants for the Mailgun integration node.

Reference: https://documentation.mailgun.com/en/latest/api-sending.html.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL_US: Final[str] = "https://api.mailgun.net"
API_BASE_URL_EU: Final[str] = "https://api.eu.mailgun.net"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_SEND_EMAIL: Final[str] = "send_email"
SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (OP_SEND_EMAIL,)

REGION_US: Final[str] = "us"
REGION_EU: Final[str] = "eu"
VALID_REGIONS: Final[frozenset[str]] = frozenset({REGION_US, REGION_EU})
