"""Shared webhook-subsystem constants.

All strings that bleed across the webhook layer live here so we never drift
between what the router accepts, what the node records, and what the
ingress route returns.
"""

from __future__ import annotations

from typing import Final

# --- URL prefixes (no leading slash in stored paths) ---
WEBHOOK_URL_PREFIX: Final[str] = "/webhook"
WEBHOOK_TEST_URL_PREFIX: Final[str] = "/webhook-test"

# --- Supported HTTP methods (uppercased) ---
SUPPORTED_METHODS: Final[tuple[str, ...]] = (
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "HEAD",
    "OPTIONS",
)

# --- Response modes a webhook-trigger node may request ---
RESPONSE_IMMEDIATELY: Final[str] = "immediately"
RESPONSE_WHEN_FINISHED: Final[str] = "when_finished"

RESPONSE_MODES: Final[tuple[str, ...]] = (RESPONSE_IMMEDIATELY, RESPONSE_WHEN_FINISHED)
