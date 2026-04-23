"""One-shot nonce consumption for SSO callbacks.

The SSO state token (:mod:`weftlyflow.auth.sso.state_token`) is signed and
expiring but otherwise **replay-safe only by virtue of its TTL**. A captured
callback URL — lifted from browser history, a reverse-proxy access log, or
an overly verbose error reporter — can be replayed within the 10-minute
validity window to re-authenticate as the original user.

This module closes that window by pairing each accepted callback with a
single-use ``(nonce, expiry)`` entry. A second arrival with the same nonce
is refused.

The :class:`NonceStore` protocol deliberately has one method, ``consume``,
so alternate backends (in-process, Redis, future SQL) all slot into the
same seam. Two backends ship in-tree:

* :class:`InMemoryNonceStore` — correct and lock-free for single-instance
  deployments; survives only as long as the process does.
* :class:`RedisNonceStore` — shared across API replicas so horizontally
  scaled deployments stay replay-safe no matter which pod terminates the
  callback. Uses ``SET NX EX`` so the first-writer-wins decision is made
  atomically on the Redis side.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from redis.asyncio import Redis


class NonceStore(Protocol):
    """Record one-shot nonces so replayed SSO callbacks are rejected.

    Implementations must be concurrency-safe under ``asyncio`` — the SSO
    callback handlers are awaited on FastAPI's main event loop and two
    racing browsers must never both observe ``True``.
    """

    async def consume(self, nonce: str, *, ttl_seconds: int) -> bool:
        """Atomically record ``nonce``.

        Args:
            nonce: Opaque identifier, already extracted from the verified
                state-token claims.
            ttl_seconds: How long the nonce stays in the store before it
                becomes eligible for eviction. Should match the state
                token's TTL.

        Returns:
            ``True`` on first use (caller may proceed), ``False`` on
            replay (caller must reject the callback).
        """


class InMemoryNonceStore:
    """Process-local :class:`NonceStore` backed by a dict + lock.

    Suitable for single-instance deployments. Memory bounds are:
    ``O(accepted_callbacks_within_TTL)`` — typically dozens at most.

    Example:
        >>> store = InMemoryNonceStore()
        >>> await store.consume("abc", ttl_seconds=600)
        True
        >>> await store.consume("abc", ttl_seconds=600)
        False
    """

    __slots__ = ("_lock", "_seen")

    def __init__(self) -> None:
        """Initialise with an empty record and a fresh asyncio lock."""
        self._seen: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def consume(self, nonce: str, *, ttl_seconds: int) -> bool:
        """See :meth:`NonceStore.consume`."""
        async with self._lock:
            now = time.monotonic()
            # Lazy eviction: cheaper than a background task and correct
            # under the expected volume. O(n) in live entries.
            if self._seen:
                self._seen = {k: exp for k, exp in self._seen.items() if exp > now}
            if nonce in self._seen:
                return False
            self._seen[nonce] = now + ttl_seconds
            return True


class RedisNonceStore:
    """Redis-backed :class:`NonceStore` for multi-instance deployments.

    Every key is namespaced under ``weftlyflow:sso:nonce:<nonce>`` so the
    store cohabits cleanly with Celery brokering and whatever else shares
    the Redis instance. The set is written with ``SET NX EX ttl``, which
    performs the first-writer-wins decision atomically on the server —
    there is no read-then-write race window.

    Example:
        >>> from redis.asyncio import Redis
        >>> client = Redis.from_url("redis://localhost:6379/0")
        >>> store = RedisNonceStore(client)
        >>> await store.consume("abc", ttl_seconds=600)
        True
        >>> await store.consume("abc", ttl_seconds=600)
        False
    """

    __slots__ = ("_client", "_key_prefix")

    def __init__(self, client: Redis, *, key_prefix: str = "weftlyflow:sso:nonce:") -> None:
        """Store the Redis client and the key prefix used for every entry.

        Args:
            client: An already-connected ``redis.asyncio.Redis`` instance.
                Caller owns its lifecycle.
            key_prefix: Namespace for nonce keys. Override in tests or when
                sharing a Redis DB across environments.
        """
        self._client = client
        self._key_prefix = key_prefix

    async def consume(self, nonce: str, *, ttl_seconds: int) -> bool:
        """See :meth:`NonceStore.consume`.

        Implementation note: ``SET key value NX EX ttl`` returns the string
        ``"OK"`` on a successful write and :data:`None` when the key already
        exists — mapping directly onto the first-use / replay distinction.
        """
        key = f"{self._key_prefix}{nonce}"
        # ``nx=True`` → only set when the key is absent. ``ex=ttl_seconds``
        # → atomically attach an expiry so an abandoned login cannot
        # pin memory forever. The sentinel value ``"1"`` is never read.
        result = await self._client.set(key, "1", nx=True, ex=ttl_seconds)
        return result is not None
