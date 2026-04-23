"""Constants for the PostHog integration node.

Reference: https://posthog.com/docs/api.
"""

from __future__ import annotations

from typing import Final

DEFAULT_HOST: Final[str] = "https://us.i.posthog.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 15.0

OP_CAPTURE: Final[str] = "capture"
OP_BATCH: Final[str] = "batch"
OP_IDENTIFY: Final[str] = "identify"
OP_ALIAS: Final[str] = "alias"
OP_DECIDE: Final[str] = "decide"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_CAPTURE,
    OP_BATCH,
    OP_IDENTIFY,
    OP_ALIAS,
    OP_DECIDE,
)
