"""Constants for the Segment integration node.

Reference: https://segment.com/docs/connections/sources/catalog/libraries/server/http-api/.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.segment.io"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 15.0

OP_TRACK: Final[str] = "track"
OP_IDENTIFY: Final[str] = "identify"
OP_GROUP: Final[str] = "group"
OP_PAGE: Final[str] = "page"
OP_ALIAS: Final[str] = "alias"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_TRACK,
    OP_IDENTIFY,
    OP_GROUP,
    OP_PAGE,
    OP_ALIAS,
)
