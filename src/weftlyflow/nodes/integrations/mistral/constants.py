"""Constants for the Mistral La Plateforme integration node.

Reference: https://docs.mistral.ai/api/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 120.0
DEFAULT_MODEL: Final[str] = "mistral-large-latest"
DEFAULT_EMBED_MODEL: Final[str] = "mistral-embed"
DEFAULT_FIM_MODEL: Final[str] = "codestral-latest"

OP_CHAT_COMPLETION: Final[str] = "chat_completion"
OP_FIM_COMPLETION: Final[str] = "fim_completion"
OP_CREATE_EMBEDDING: Final[str] = "create_embedding"
OP_LIST_MODELS: Final[str] = "list_models"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_CHAT_COMPLETION,
    OP_FIM_COMPLETION,
    OP_CREATE_EMBEDDING,
    OP_LIST_MODELS,
)
