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
because the only question the SSO layer ever asks is *"is this the first
time I've seen this nonce?"* Keeping the surface that small lets a future
Redis-backed implementation drop in without rewrites.

The shipped implementation, :class:`InMemoryNonceStore`, is a dict guarded
by an :class:`asyncio.Lock` with lazy eviction on write. It closes the
replay window for single-instance self-hosted installs — the default
deployment shape. Multi-instance deployments need a shared store (Redis
``SET NX EX``); that will arrive as a follow-on tranche.
"""

from __future__ import annotations

import asyncio
import time
from typing import Protocol


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
