"""Celery tasks that consume the execution queue.

One task today — :func:`execute_workflow` — drains the ``executions`` queue.
Each task body is deliberately small: marshal the payload, acquire an
idempotency claim, delegate to :mod:`weftlyflow.worker.execution`, release.

The module also exposes :func:`register_tasks` so the Celery app can wire
them without import-cycles against the rest of the worker package.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import structlog

from weftlyflow.worker.app import celery_app
from weftlyflow.worker.idempotency import IdempotencyGuard, NullIdempotencyGuard
from weftlyflow.worker.queue import ExecutionRequest

log = structlog.get_logger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="weftlyflow.execute_workflow",
    queue="executions",
    acks_late=True,
    max_retries=3,
    default_retry_delay=5,
)
def execute_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the workflow described by ``payload`` and return a summary dict.

    The payload is the dict form of :class:`ExecutionRequest`. Returning a
    dict (rather than ``None``) lets callers inspect the status via Celery's
    result backend if they want.
    """
    request = ExecutionRequest.from_dict(payload)
    owner = f"worker:{os.getpid()}"

    guard = _idempotency_guard()
    if not guard.claim(request.execution_id, owner=owner):
        log.info("execute_workflow_skip_duplicate", execution_id=request.execution_id)
        return {"execution_id": request.execution_id, "status": "skipped"}

    try:
        session_factory, registry = _resolve_worker_resources()
        from weftlyflow.worker.execution import run_execution_sync  # noqa: PLC0415

        execution = run_execution_sync(
            request, session_factory=session_factory, registry=registry,
        )
    finally:
        guard.release(request.execution_id)

    if execution is None:
        return {"execution_id": request.execution_id, "status": "missing_workflow"}
    return {"execution_id": execution.id, "status": execution.status}


def _idempotency_guard() -> IdempotencyGuard | NullIdempotencyGuard:
    # Import inside the function so importing `tasks` does not open a Redis
    # connection at module load — useful for tests that use eager mode.
    client = _redis_client()
    if client is None:
        return NullIdempotencyGuard()
    return IdempotencyGuard(client)


@lru_cache(maxsize=1)
def _redis_client() -> Any | None:
    try:
        import redis  # noqa: PLC0415

        from weftlyflow.config import get_settings  # noqa: PLC0415
    except ImportError:  # pragma: no cover — redis is a required dep but belt-and-braces
        return None
    try:
        return redis.Redis.from_url(get_settings().redis_url)
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("redis_unreachable", error=str(exc))
        return None


@lru_cache(maxsize=1)
def _resolve_worker_resources() -> tuple[Any, Any]:
    """Create a sync-friendly session factory + node registry for the worker.

    Cached per-process so Celery's pool reuses a single engine across tasks.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415

    from weftlyflow.config import get_settings  # noqa: PLC0415
    from weftlyflow.nodes.registry import NodeRegistry  # noqa: PLC0415

    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    registry = NodeRegistry()
    registry.load_builtins()
    return session_factory, registry


def register_tasks() -> None:
    """Import side-effect: make Celery aware of :func:`execute_workflow`.

    Called by :mod:`weftlyflow.worker.app` on Celery startup. Safe to call
    multiple times — the decorator above is idempotent.
    """
    # The mere act of importing this module registers the task — this
    # function exists to make that intent explicit in the wiring code.
    return None
