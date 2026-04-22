"""Constants for the Google Sheets integration node.

Reference: https://developers.google.com/sheets/api/reference/rest.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://sheets.googleapis.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_READ_RANGE: Final[str] = "read_range"
OP_APPEND_ROW: Final[str] = "append_row"
OP_UPDATE_RANGE: Final[str] = "update_range"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_READ_RANGE,
    OP_APPEND_ROW,
    OP_UPDATE_RANGE,
)

VALUE_INPUT_USER_ENTERED: Final[str] = "USER_ENTERED"
VALUE_INPUT_RAW: Final[str] = "RAW"
VALID_VALUE_INPUT_OPTIONS: Final[frozenset[str]] = frozenset(
    {VALUE_INPUT_USER_ENTERED, VALUE_INPUT_RAW},
)
