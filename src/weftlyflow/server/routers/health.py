"""Health and readiness endpoints.

- ``GET /healthz`` — liveness. Returns 200 if the process is up.
- ``GET /readyz`` — readiness. Pings the database; returns 503 if the DB is
  unreachable so orchestrators don't route traffic to a broken instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from weftlyflow import __version__
from weftlyflow.server.deps import get_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    """Return a small JSON blob proving the process is alive."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz", summary="Readiness probe")
async def readyz(request: Request, session: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Return readiness status — checks DB + registry state."""
    payload = {"status": "ready", "version": __version__}
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        _log.warning("readyz_db_failure", error=str(exc))
        payload["status"] = "degraded"
        payload["database"] = "unreachable"
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)

    registry = getattr(request.app.state, "node_registry", None)
    payload["nodes"] = str(len(registry) if registry is not None else 0)
    return JSONResponse(status_code=status.HTTP_200_OK, content=payload)
