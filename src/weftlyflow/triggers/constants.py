"""Shared trigger-subsystem constants.

Lock keys, default TTLs, and the set of recognised schedule kinds. Keeping
them here means the tests and the production code both reference the same
symbols.
"""

from __future__ import annotations

from typing import Final

LEADER_LOCK_KEY: Final[str] = "weftlyflow:leader:lock"
LEADER_LOCK_TTL_SECONDS: Final[int] = 30
LEADER_REFRESH_INTERVAL_SECONDS: Final[int] = 10

SCHEDULE_KIND_CRON: Final[str] = "cron"
SCHEDULE_KIND_INTERVAL: Final[str] = "interval"

SCHEDULE_KINDS: Final[tuple[str, ...]] = (SCHEDULE_KIND_CRON, SCHEDULE_KIND_INTERVAL)
