"""Constants for the Notion integration node.

Reference: https://developers.notion.com/reference/intro.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.notion.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
DEFAULT_NOTION_VERSION: Final[str] = "2022-06-28"

OP_QUERY_DATABASE: Final[str] = "query_database"
OP_CREATE_PAGE: Final[str] = "create_page"
OP_RETRIEVE_PAGE: Final[str] = "retrieve_page"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_QUERY_DATABASE,
    OP_CREATE_PAGE,
    OP_RETRIEVE_PAGE,
)

DEFAULT_PAGE_SIZE: Final[int] = 100
MAX_PAGE_SIZE: Final[int] = 100
