"""Unit tests for :mod:`weftlyflow.auth.sso.nonce_store`."""

from __future__ import annotations

import asyncio

from weftlyflow.auth.sso.nonce_store import InMemoryNonceStore


async def test_first_consume_returns_true() -> None:
    store = InMemoryNonceStore()

    assert await store.consume("alpha", ttl_seconds=60) is True


async def test_second_consume_returns_false() -> None:
    store = InMemoryNonceStore()

    assert await store.consume("alpha", ttl_seconds=60) is True
    assert await store.consume("alpha", ttl_seconds=60) is False


async def test_distinct_nonces_do_not_collide() -> None:
    store = InMemoryNonceStore()

    assert await store.consume("alpha", ttl_seconds=60) is True
    assert await store.consume("beta", ttl_seconds=60) is True


async def test_ttl_expiry_allows_reuse() -> None:
    """A nonce past its TTL is evicted on the next consume."""
    store = InMemoryNonceStore()

    # TTL of zero seconds: the nonce's expiry is "now + 0", which is <= now
    # on the following consume call → eligible for eviction.
    assert await store.consume("alpha", ttl_seconds=0) is True
    # Yield so the monotonic clock advances at least a tick.
    await asyncio.sleep(0)
    assert await store.consume("alpha", ttl_seconds=60) is True


async def test_concurrent_consumes_resolve_to_single_winner() -> None:
    """Two coroutines racing on the same nonce — exactly one must win."""
    store = InMemoryNonceStore()

    results = await asyncio.gather(
        store.consume("shared", ttl_seconds=60),
        store.consume("shared", ttl_seconds=60),
        store.consume("shared", ttl_seconds=60),
    )

    assert results.count(True) == 1
    assert results.count(False) == 2
