"""Domain-level constants — string tokens every layer can safely import.

Lives in :mod:`weftlyflow.domain` because the port vocabulary is a *model*
concept, not a *runtime* concept. Putting it here lets both the engine and
node packages reference the same strings without creating a cross-layer
dependency.
"""

from __future__ import annotations

from typing import Final

MAIN_PORT: Final[str] = "main"
TRUE_PORT: Final[str] = "true"
FALSE_PORT: Final[str] = "false"

DEFAULT_SOURCE_INDEX: Final[int] = 0
DEFAULT_TARGET_INDEX: Final[int] = 0
