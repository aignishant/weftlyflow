"""Shared pytest fixtures.

Phase-0: minimal — just ensure env defaults are sane for tests that touch
settings. Phase-2 expands this file with DB fixtures (transactional rollback)
and a ``httpx.AsyncClient`` against the FastAPI app.
"""

from __future__ import annotations

import os

os.environ.setdefault("WEFTLYFLOW_ENV", "test")
os.environ.setdefault("WEFTLYFLOW_LOG_LEVEL", "warning")
os.environ.setdefault("WEFTLYFLOW_LOG_FORMAT", "console")
os.environ.setdefault("WEFTLYFLOW_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("WEFTLYFLOW_REDIS_URL", "redis://localhost:6379/15")
