"""Constants for the Google Generative Language integration node.

Reference: https://ai.google.dev/api/rest.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 120.0
DEFAULT_MODEL: Final[str] = "gemini-1.5-flash"

OP_GENERATE_CONTENT: Final[str] = "generate_content"
OP_COUNT_TOKENS: Final[str] = "count_tokens"
OP_LIST_MODELS: Final[str] = "list_models"
OP_GET_MODEL: Final[str] = "get_model"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GENERATE_CONTENT,
    OP_COUNT_TOKENS,
    OP_LIST_MODELS,
    OP_GET_MODEL,
)
