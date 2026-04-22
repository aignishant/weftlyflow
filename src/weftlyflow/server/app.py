"""FastAPI app factory.

Wires:

* Structlog configuration.
* Async SQLAlchemy engine + session factory.
* Alembic-managed schema (auto-upgraded in dev, verified in prod).
* First-boot admin + project seed.
* Node registry with built-in nodes preloaded.
* Request-id + access-log middleware.
* Domain-exception → HTTP-response handlers.
* All Phase-2 routers.

A module-level ``app`` is exposed so ``uvicorn weftlyflow.server.app:app`` just
works. Tests use :func:`create_app` to spin up isolated instances with
overridden settings/session factories.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from weftlyflow import __version__
from weftlyflow.auth.bootstrap import ensure_bootstrap_admin
from weftlyflow.config import get_settings
from weftlyflow.config.logging import configure_logging
from weftlyflow.credentials.cipher import CredentialCipher, generate_key
from weftlyflow.credentials.registry import CredentialTypeRegistry
from weftlyflow.credentials.resolver import DatabaseCredentialResolver
from weftlyflow.db.base import Base
from weftlyflow.db.entities import (  # noqa: F401 — register tables on Base.metadata
    CredentialEntity,
    ExecutionDataEntity,
    ExecutionEntity,
    OAuthStateEntity,
    ProjectEntity,
    RefreshTokenEntity,
    TriggerScheduleEntity,
    UserEntity,
    WebhookEntity,
    WorkflowEntity,
)
from weftlyflow.nodes.registry import NodeRegistry
from weftlyflow.server.errors import register_exception_handlers
from weftlyflow.server.middleware import RequestContextMiddleware
from weftlyflow.server.routers import auth as auth_router
from weftlyflow.server.routers import credentials as credentials_router
from weftlyflow.server.routers import executions as executions_router
from weftlyflow.server.routers import health as health_router
from weftlyflow.server.routers import node_types as node_types_router
from weftlyflow.server.routers import oauth2 as oauth2_router
from weftlyflow.server.routers import webhooks_ingress as webhooks_ingress_router
from weftlyflow.server.routers import workflows as workflows_router
from weftlyflow.triggers.leader import InMemoryLeaderLock
from weftlyflow.triggers.manager import ActiveTriggerManager
from weftlyflow.triggers.scheduler import InMemoryScheduler
from weftlyflow.webhooks.registry import WebhookRegistry
from weftlyflow.worker.queue import InlineExecutionQueue

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bootstrap shared resources at startup, tear down at shutdown."""
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    log.info("weftlyflow_starting", version=__version__, env=settings.env)

    engine: AsyncEngine = create_async_engine(settings.database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    registry = NodeRegistry()
    registry.load_builtins()

    async with session_factory() as session:
        await ensure_bootstrap_admin(
            session,
            settings,
            admin_email_env=os.getenv("WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL"),
            admin_password_env=os.getenv("WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD"),
        )
        await session.commit()

    encryption_key = settings.encryption_key.get_secret_value()
    if not encryption_key:
        encryption_key = generate_key()
        log.warning("encryption_key_missing_using_ephemeral")
    old_keys = [k.strip() for k in settings.encryption_key_old_keys.split(",") if k.strip()]
    credential_cipher = CredentialCipher(encryption_key, old_keys=old_keys)

    credential_types = CredentialTypeRegistry()
    credential_types.load_builtins()

    credential_resolver = DatabaseCredentialResolver(
        session_factory=session_factory,
        cipher=credential_cipher,
        types=credential_types,
    )

    webhook_registry = WebhookRegistry()
    scheduler = InMemoryScheduler()
    leader = InMemoryLeaderLock(instance_id="api")
    leader.acquire()
    execution_queue = InlineExecutionQueue(
        session_factory=session_factory,
        registry=registry,
        credential_resolver=credential_resolver,
    )
    trigger_manager = ActiveTriggerManager(
        session_factory=session_factory,
        registry=webhook_registry,
        scheduler=scheduler,
        queue=execution_queue,
        leader=leader,
    )
    await trigger_manager.warm_up()
    scheduler.start()

    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.node_registry = registry
    app.state.webhook_registry = webhook_registry
    app.state.execution_queue = execution_queue
    app.state.trigger_manager = trigger_manager
    app.state.scheduler = scheduler
    app.state.leader_lock = leader
    app.state.credential_cipher = credential_cipher
    app.state.credential_types = credential_types
    app.state.credential_resolver = credential_resolver

    try:
        yield
    finally:
        scheduler.shutdown()
        leader.release()
        await engine.dispose()
        log.info("weftlyflow_stopped")


def create_app() -> FastAPI:
    """Return a fresh FastAPI instance wired with middleware, handlers, routers."""
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

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(workflows_router.router)
    app.include_router(executions_router.router)
    app.include_router(node_types_router.router)
    app.include_router(credentials_router.router)
    app.include_router(credentials_router.credential_types_router)
    app.include_router(oauth2_router.router)
    app.include_router(webhooks_ingress_router.router)

    return app


app = create_app()
