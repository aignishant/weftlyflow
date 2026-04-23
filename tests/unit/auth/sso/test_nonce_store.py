"""Unit tests for :mod:`weftlyflow.auth.sso.nonce_store`."""

from __future__ import annotations

import asyncio

import fakeredis.aioredis
import pytest

from weftlyflow.auth.sso.nonce_store import InMemoryNonceStore, RedisNonceStore


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


@pytest.fixture
async def redis_store() -> RedisNonceStore:
    """Return a fakeredis-backed :class:`RedisNonceStore`."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return RedisNonceStore(client, key_prefix="test:nonce:")


async def test_redis_first_consume_returns_true(redis_store: RedisNonceStore) -> None:
    assert await redis_store.consume("alpha", ttl_seconds=60) is True


async def test_redis_second_consume_returns_false(redis_store: RedisNonceStore) -> None:
    assert await redis_store.consume("alpha", ttl_seconds=60) is True
    assert await redis_store.consume("alpha", ttl_seconds=60) is False


async def test_redis_distinct_nonces_do_not_collide(redis_store: RedisNonceStore) -> None:
    assert await redis_store.consume("alpha", ttl_seconds=60) is True
    assert await redis_store.consume("beta", ttl_seconds=60) is True


async def test_redis_key_respects_prefix() -> None:
    """The store must not collide with unrelated keys on the same Redis DB."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisNonceStore(client, key_prefix="weftlyflow:sso:nonce:")

    await store.consume("alpha", ttl_seconds=60)

    # The key should be under the configured prefix, not the bare nonce.
    assert await client.exists("weftlyflow:sso:nonce:alpha") == 1
    assert await client.exists("alpha") == 0


async def test_redis_consume_sets_ttl() -> None:
    """The nonce key must carry the configured TTL — no pinned entries."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisNonceStore(client, key_prefix="test:nonce:")

    await store.consume("alpha", ttl_seconds=600)

    # fakeredis honours TTL; 0 < ttl <= 600 proves EX was attached.
    ttl = await client.ttl("test:nonce:alpha")
    assert 0 < ttl <= 600
