"""Idempotency guards for the execution queue.

Celery's default delivery semantics are *at-least-once*. A transient broker
error can drop the same task on multiple workers. To keep one logical
execution from persisting twice, we gate the task body with a Redis SETNX
on ``weftlyflow:execution:{id}`` — whichever worker wins the race proceeds;
everyone else exits early.

The guard is optional: if ``WEFTLYFLOW_IDEMPOTENCY_ENABLED=false`` or Redis is
unreachable, :class:`IdempotencyGuard` logs a warning and lets the task run
(the default production posture is "don't let a Redis outage block runs").
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Iterator

log = structlog.get_logger(__name__)

_DEFAULT_PREFIX = "weftlyflow:execution:"
_DEFAULT_TTL_SECONDS = 60 * 60  # 1h — well above any single-workflow runtime budget.


class IdempotencyGuard:
    """Thin wrapper over a Redis-like client exposing ``SET NX EX``.

    Any object that mimics ``redis.Redis.set(key, value, nx=True, ex=...)``
    and ``redis.Redis.delete(key)`` works — production uses redis-py, tests
    use :class:`fakeredis.FakeRedis`.
    """

    __slots__ = ("_client", "_prefix", "_ttl")

    def __init__(
        self,
        client: Any,
        *,
        prefix: str = _DEFAULT_PREFIX,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        """Bind to a Redis-like client."""
        self._client = client
        self._prefix = prefix
        self._ttl = ttl_seconds

    def _key(self, execution_id: str) -> str:
        return f"{self._prefix}{execution_id}"

    def claim(self, execution_id: str, *, owner: str) -> bool:
        """Return True if the caller wins the race for ``execution_id``.

        A False return means another worker (or an earlier attempt of this
        same worker) already claimed the id. The caller should abort.
        """
        try:
            acquired = self._client.set(
                self._key(execution_id),
                owner,
                nx=True,
                ex=self._ttl,
            )
        except Exception as exc:  # pragma: no cover — defensive fallback
            log.warning(
                "idempotency_unavailable",
                error=str(exc),
                execution_id=execution_id,
            )
            return True
        return bool(acquired)

    def release(self, execution_id: str) -> None:
        """Drop the claim so retries of the same id can proceed cleanly."""
        try:
            self._client.delete(self._key(execution_id))
        except Exception as exc:  # pragma: no cover — defensive fallback
            log.warning(
                "idempotency_release_failed",
                error=str(exc),
                execution_id=execution_id,
            )

    @contextmanager
    def scope(self, execution_id: str, *, owner: str) -> Iterator[bool]:
        """Context manager variant that releases on exit.

        Usage::

            with guard.scope(execution_id, owner="worker-1") as won:
                if not won:
                    return
                _do_work()
        """
        won = self.claim(execution_id, owner=owner)
        try:
            yield won
        finally:
            if won:
                self.release(execution_id)


class NullIdempotencyGuard:
    """No-op guard used when Redis is not configured.

    Always claims, never releases. Keeps the call sites uniform.
    """

    __slots__ = ()

    def claim(self, execution_id: str, *, owner: str) -> bool:
        """Always claim."""
        del execution_id, owner
        return True

    def release(self, execution_id: str) -> None:
        """No-op release."""
        del execution_id

    @contextmanager
    def scope(self, execution_id: str, *, owner: str) -> Iterator[bool]:
        """Yield True unconditionally — keeps the call site uniform."""
        del execution_id, owner
        yield True
