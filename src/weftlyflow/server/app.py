"""FastAPI app factory.

Exposes a ready-to-serve ``app`` instance for ``uvicorn weftlyflow.server.app:app``
while keeping :func:`create_app` available for tests that want a fresh instance.

Phase-0 skeleton: wires config + structlog + health. Subsequent phases add
routers, auth, DB middleware, WebSocket streams.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from weftlyflow import __version__
from weftlyflow.config import get_settings
from weftlyflow.config.logging import configure_logging
from weftlyflow.server.routers import health

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Bootstrap shared resources at startup, tear down at shutdown."""
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    log.info("weftlyflow_starting", version=__version__, env=settings.env)
    yield
    log.info("weftlyflow_stopped")


def create_app() -> FastAPI:
    """Return a fresh FastAPI instance wired with middleware and routers.

    Kept as a factory so tests can spin up isolated apps without sharing state.
    """
    settings = get_settings()

    app = FastAPI(
        title="Weftlyflow",
        version=__version__,
        description="Workflow automation platform.",
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    # Routers added in Phase 2:
    # app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    # app.include_router(workflows.router, prefix="/api/v1/workflows", tags=["workflows"])
    # ...

    return app


app = create_app()
