"""Shared fixtures for Phase-2 integration tests.

Every test gets:

* a fresh in-memory SQLite database,
* a :class:`weftlyflow.nodes.registry.NodeRegistry` preloaded with built-ins,
* a FastAPI app whose ``app.state`` is wired to the above,
* an :class:`httpx.AsyncClient` pointed at the app's ASGI transport,
* a bootstrap admin already created with a known email + password.

The setup runs **without** the lifespan context (so we can control it
explicitly per test); instead the fixture performs the equivalent steps
inline and lets ``pytest-asyncio`` manage the event loop.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from weftlyflow.auth.bootstrap import ensure_bootstrap_admin
from weftlyflow.config import get_settings
from weftlyflow.db.base import Base
from weftlyflow.db.entities import (  # noqa: F401 — register tables on Base.metadata
    ExecutionDataEntity,
    ExecutionEntity,
    ProjectEntity,
    RefreshTokenEntity,
    UserEntity,
    WorkflowEntity,
)
from weftlyflow.nodes.registry import NodeRegistry
from weftlyflow.server.app import create_app

TEST_ADMIN_EMAIL: str = "admin@test.weftlyflow"
TEST_ADMIN_PASSWORD: str = "integration-test-pw"


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    """Ensure every test sees fresh settings values for our env tweaks."""
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Yield an :class:`AsyncClient` wired to a fully-bootstrapped app."""
    os.environ["WEFTLYFLOW_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ.setdefault(
        "WEFTLYFLOW_SECRET_KEY",
        "integration-test-secret-key-32-bytes-plus-padding-0123456789",
    )
    get_settings.cache_clear()
    settings = get_settings()

    engine = create_async_engine(settings.database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    registry = NodeRegistry()
    registry.load_builtins()

    async with session_factory() as session:
        await ensure_bootstrap_admin(
            session,
            settings,
            admin_email_env=TEST_ADMIN_EMAIL,
            admin_password_env=TEST_ADMIN_PASSWORD,
        )
        await session.commit()

    app = create_app()
    # Replace lifespan-driven state with our pre-built resources:
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.node_registry = registry
    # Force the app NOT to run its lifespan (we already did the work):
    app.router.lifespan_context = _noop_lifespan  # type: ignore[assignment]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await engine.dispose()


async def _noop_lifespan(_app: object) -> AsyncIterator[None]:
    """Replacement lifespan used by the integration fixture.

    The fixture has already created the engine/session factory/registry, so
    the app's normal lifespan must become a no-op to avoid double-creation
    and avoid re-running the bootstrap check.
    """
    yield


@pytest_asyncio.fixture
async def access_token(client: AsyncClient) -> str:
    """Return a valid bearer token for the bootstrap admin."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


@pytest_asyncio.fixture
async def auth_headers(access_token: str) -> dict[str, str]:
    """Return an ``Authorization: Bearer ...`` header dict."""
    return {"Authorization": f"Bearer {access_token}"}
