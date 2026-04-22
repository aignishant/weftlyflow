"""Redis-backed leader election for the trigger manager.

Only one instance of Weftlyflow should own active-trigger state at a time
(APScheduler jobs, webhook installation against external services). A
simple ``SET key val NX EX`` lock gives at-most-one semantics without the
operational burden of a full consensus system.

Usage::

    lock = LeaderLock(redis_client, instance_id="api-1")
    if lock.acquire():
        # We are the leader; start the scheduler.
        ...
    lock.refresh()  # call periodically from a background task.
    lock.release()  # on shutdown.

Testing uses :class:`InMemoryLock` which exposes the same surface without a
Redis dependency.
"""

from __future__ import annotations

from typing import Any, Protocol

import structlog

from weftlyflow.triggers.constants import (
    LEADER_LOCK_KEY,
    LEADER_LOCK_TTL_SECONDS,
)

log = structlog.get_logger(__name__)


class LeaderLock(Protocol):
    """Minimal contract shared by Redis-backed + in-memory implementations."""

    instance_id: str

    def acquire(self) -> bool:
        """Return True if this instance now holds the leadership lock."""

    def refresh(self) -> bool:
        """Re-assert the lock's TTL. Returns True iff still leader."""

    def release(self) -> None:
        """Release the lock if held. Safe to call unconditionally."""

    def is_leader(self) -> bool:
        """Return the most recent view of leadership status."""


class RedisLeaderLock:
    """``SET NX EX`` style leader lock over a redis-py-compatible client."""

    __slots__ = ("_client", "_held", "_key", "_ttl", "instance_id")

    def __init__(
        self,
        client: Any,
        *,
        instance_id: str,
        key: str = LEADER_LOCK_KEY,
        ttl_seconds: int = LEADER_LOCK_TTL_SECONDS,
    ) -> None:
        """Bind to ``client`` and configure the lock key."""
        self._client = client
        self._key = key
        self._ttl = ttl_seconds
        self._held = False
        self.instance_id = instance_id

    def acquire(self) -> bool:
        """Attempt to claim leadership; returns ``self.is_leader()``."""
        try:
            acquired = self._client.set(self._key, self.instance_id, nx=True, ex=self._ttl)
        except Exception as exc:  # pragma: no cover — defensive
            log.warning("leader_acquire_failed", error=str(exc))
            self._held = False
            return False
        self._held = bool(acquired)
        if self._held:
            log.info("leader_acquired", instance_id=self.instance_id)
        return self._held

    def refresh(self) -> bool:
        """Extend the TTL iff the current owner is still this instance."""
        try:
            current = self._client.get(self._key)
        except Exception as exc:  # pragma: no cover — defensive
            log.warning("leader_refresh_failed", error=str(exc))
            return False
        if current is None:
            return self.acquire()
        if _decode(current) != self.instance_id:
            self._held = False
            return False
        try:
            self._client.expire(self._key, self._ttl)
        except Exception as exc:  # pragma: no cover — defensive
            log.warning("leader_refresh_expire_failed", error=str(exc))
            return self._held
        self._held = True
        return True

    def release(self) -> None:
        """Release leadership iff held by this instance."""
        if not self._held:
            return
        try:
            current = self._client.get(self._key)
            if current is not None and _decode(current) == self.instance_id:
                self._client.delete(self._key)
                log.info("leader_released", instance_id=self.instance_id)
        except Exception as exc:  # pragma: no cover — defensive
            log.warning("leader_release_failed", error=str(exc))
        finally:
            self._held = False

    def is_leader(self) -> bool:
        """Return the last observed leadership state without network IO."""
        return self._held


class InMemoryLeaderLock:
    """In-process leader lock for tests and single-instance deployments."""

    __slots__ = ("_held", "instance_id")

    def __init__(self, *, instance_id: str = "single") -> None:
        """Create an always-acquirable lock."""
        self.instance_id = instance_id
        self._held = False

    def acquire(self) -> bool:
        """Always succeed — single-instance deployments are always leader."""
        self._held = True
        return True

    def refresh(self) -> bool:
        """Return the current held state."""
        return self._held

    def release(self) -> None:
        """Clear the held flag."""
        self._held = False

    def is_leader(self) -> bool:
        """Return the current held state."""
        return self._held


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
