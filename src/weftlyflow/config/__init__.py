"""Runtime configuration — Pydantic Settings + structlog setup.

`weftlyflow.config.settings.WeftlyflowSettings` is the single source of truth for
every environment-driven value. Never read ``os.environ`` directly from other
modules — request the settings object instead.

Import pattern:
    from weftlyflow.config import get_settings
    settings = get_settings()

See Also:
    - IMPLEMENTATION_BIBLE.md §4 (technology stack) for the full list of env vars.
    - ``.env.example`` at the repo root for defaults.
"""

from __future__ import annotations

from weftlyflow.config.settings import WeftlyflowSettings, get_settings

__all__ = ["WeftlyflowSettings", "get_settings"]
