"""Engine and session factories.

Settings are read lazily — calling these functions before the settings are
configured (e.g. in a unit test that tweaks ``WEFTLYFLOW_*`` env vars) will pick
up the new values as long as the engine hasn't been cached yet. Tests that
mutate settings should call :func:`reset_engines` in their teardown.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from weftlyflow.config import get_settings


def _sync_url(url: str) -> str:
    """Rewrite an async URL to its sync equivalent (best effort)."""
    return (
        url.replace("+aiosqlite", "")
        .replace("+asyncpg", "+psycopg")
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a cached synchronous SQLAlchemy engine.

    Used by Alembic migrations and any code path that is genuinely sync
    (Celery tasks default to sync sessions).
    """
    return create_engine(_sync_url(get_settings().database_url), pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_async_engine() -> AsyncEngine:
    """Return a cached asynchronous SQLAlchemy engine (for FastAPI handlers)."""
    return create_async_engine(get_settings().database_url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)


@lru_cache(maxsize=1)
def _async_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_async_engine(), expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a sync session that commits on clean exit, rolls back on error.

    Example:
        >>> with session_scope() as db:
        ...     db.add(obj)
    """
    db = _session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def reset_engines() -> None:
    """Dispose cached engines — call from test teardown after mutating env."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
        get_engine.cache_clear()
    if get_async_engine.cache_info().currsize:
        # AsyncEngine.dispose() is a coroutine; tests own the loop, skip here.
        get_async_engine.cache_clear()
    _session_factory.cache_clear()
    _async_session_factory.cache_clear()
