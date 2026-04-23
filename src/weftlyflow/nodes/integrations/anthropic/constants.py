"""Constants for the Anthropic integration node.

Reference: https://docs.anthropic.com/en/api/getting-started.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 120.0
DEFAULT_MODEL: Final[str] = "claude-3-5-sonnet-latest"
DEFAULT_MAX_TOKENS: Final[int] = 1024

OP_CREATE_MESSAGE: Final[str] = "create_message"
OP_COUNT_TOKENS: Final[str] = "count_tokens"
OP_LIST_MODELS: Final[str] = "list_models"
OP_GET_MODEL: Final[str] = "get_model"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_CREATE_MESSAGE,
    OP_COUNT_TOKENS,
    OP_LIST_MODELS,
    OP_GET_MODEL,
)
