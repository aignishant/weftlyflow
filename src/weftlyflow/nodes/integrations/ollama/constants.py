"""Constants for the Ollama integration node.

Reference: https://github.com/ollama/ollama/blob/main/docs/api.md.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 300.0
"""Local inference is slow on CPU; 5 min is the documented Ollama client default."""

DEFAULT_MODEL: Final[str] = "llama3.2"

OP_GENERATE: Final[str] = "generate"
OP_CHAT: Final[str] = "chat"
OP_EMBEDDINGS: Final[str] = "embeddings"
OP_LIST_MODELS: Final[str] = "list_models"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_GENERATE,
    OP_CHAT,
    OP_EMBEDDINGS,
    OP_LIST_MODELS,
)
