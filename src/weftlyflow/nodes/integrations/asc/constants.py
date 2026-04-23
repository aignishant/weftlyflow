"""Constants for the Apple App Store Connect integration node.

Reference: https://developer.apple.com/documentation/appstoreconnectapi.
"""

from __future__ import annotations

from typing import Final

API_BASE_URL: Final[str] = "https://api.appstoreconnect.apple.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_LIST_APPS: Final[str] = "list_apps"
OP_GET_APP: Final[str] = "get_app"
OP_LIST_BUILDS: Final[str] = "list_builds"
OP_LIST_BETA_TESTERS: Final[str] = "list_beta_testers"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_LIST_APPS,
    OP_GET_APP,
    OP_LIST_BUILDS,
    OP_LIST_BETA_TESTERS,
)
