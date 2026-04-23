"""Constants for the OpenAI integration node.

Reference: https://platform.openai.com/docs/api-reference.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.openai.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 120.0

OP_CHAT_COMPLETION: Final[str] = "chat_completion"
OP_CREATE_EMBEDDING: Final[str] = "create_embedding"
OP_LIST_MODELS: Final[str] = "list_models"
OP_GET_MODEL: Final[str] = "get_model"
OP_CREATE_MODERATION: Final[str] = "create_moderation"
OP_CREATE_IMAGE: Final[str] = "create_image"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_CHAT_COMPLETION,
    OP_CREATE_EMBEDDING,
    OP_LIST_MODELS,
    OP_GET_MODEL,
    OP_CREATE_MODERATION,
    OP_CREATE_IMAGE,
)

VALID_IMAGE_SIZES: Final[frozenset[str]] = frozenset(
    {"256x256", "512x512", "1024x1024", "1024x1792", "1792x1024"},
)
VALID_RESPONSE_FORMATS: Final[frozenset[str]] = frozenset({"url", "b64_json"})
