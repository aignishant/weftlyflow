"""Health and readiness endpoints.

- ``GET /healthz`` — liveness. Returns 200 if the process is up.
- ``GET /readyz``  — readiness. In Phase 2 this pings the DB and Redis; for
  now it simply mirrors liveness.
"""

from __future__ import annotations

from fastapi import APIRouter

from weftlyflow import __version__

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    """Return a small JSON blob proving the process is alive."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz", summary="Readiness probe")
async def readyz() -> dict[str, str]:
    """Return readiness status. Phase-0: mirrors liveness."""
    return {"status": "ready", "version": __version__}
