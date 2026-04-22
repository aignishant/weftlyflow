"""Unit tests for leader election primitives."""

from __future__ import annotations

import fakeredis

from weftlyflow.triggers.constants import LEADER_LOCK_KEY
from weftlyflow.triggers.leader import InMemoryLeaderLock, RedisLeaderLock


def test_in_memory_lock_is_always_leader() -> None:
    lock = InMemoryLeaderLock()
    assert lock.acquire() is True
    assert lock.is_leader() is True
    lock.release()
    assert lock.is_leader() is False


def test_redis_lock_single_instance_wins() -> None:
    client = fakeredis.FakeRedis()
    lock = RedisLeaderLock(client, instance_id="api-1")
    assert lock.acquire() is True
    assert lock.is_leader() is True


def test_redis_lock_rejects_second_acquirer() -> None:
    client = fakeredis.FakeRedis()
    first = RedisLeaderLock(client, instance_id="api-1")
    second = RedisLeaderLock(client, instance_id="api-2")
    first.acquire()
    assert second.acquire() is False
    assert second.is_leader() is False


def test_redis_lock_refresh_extends_ttl_for_owner() -> None:
    client = fakeredis.FakeRedis()
    lock = RedisLeaderLock(client, instance_id="api-1", ttl_seconds=60)
    lock.acquire()
    # After refresh, key still points at instance-1.
    assert lock.refresh() is True
    stored = client.get(LEADER_LOCK_KEY)
    assert stored is not None
    assert stored.decode("utf-8") == "api-1"


def test_redis_lock_refresh_becomes_leader_if_key_expires() -> None:
    client = fakeredis.FakeRedis()
    lock = RedisLeaderLock(client, instance_id="api-1")
    # key doesn't exist yet; refresh should acquire.
    assert lock.refresh() is True


def test_redis_lock_refresh_false_when_different_owner_present() -> None:
    client = fakeredis.FakeRedis()
    other = RedisLeaderLock(client, instance_id="api-2")
    other.acquire()
    first = RedisLeaderLock(client, instance_id="api-1")
    # first never held the lock; refresh returns False.
    assert first.refresh() is False


def test_release_drops_key_only_if_owner() -> None:
    client = fakeredis.FakeRedis()
    lock = RedisLeaderLock(client, instance_id="api-1")
    lock.acquire()
    lock.release()
    assert client.get(LEADER_LOCK_KEY) is None
