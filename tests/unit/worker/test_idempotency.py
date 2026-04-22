"""Unit tests for :mod:`weftlyflow.worker.idempotency`."""

from __future__ import annotations

import fakeredis

from weftlyflow.worker.idempotency import IdempotencyGuard, NullIdempotencyGuard


def test_claim_succeeds_only_once() -> None:
    guard = IdempotencyGuard(fakeredis.FakeRedis())
    assert guard.claim("ex_1", owner="worker-a") is True
    assert guard.claim("ex_1", owner="worker-b") is False


def test_release_lets_new_owner_claim() -> None:
    guard = IdempotencyGuard(fakeredis.FakeRedis())
    guard.claim("ex_1", owner="a")
    guard.release("ex_1")
    assert guard.claim("ex_1", owner="b") is True


def test_scope_context_manager_releases_on_exit() -> None:
    guard = IdempotencyGuard(fakeredis.FakeRedis())
    with guard.scope("ex_1", owner="a") as won:
        assert won is True
    # After exit the key is free again.
    assert guard.claim("ex_1", owner="b") is True


def test_scope_yields_false_when_losing_race() -> None:
    guard = IdempotencyGuard(fakeredis.FakeRedis())
    guard.claim("ex_1", owner="a")
    with guard.scope("ex_1", owner="b") as won:
        assert won is False


def test_null_guard_always_claims() -> None:
    guard = NullIdempotencyGuard()
    assert guard.claim("ex_1", owner="a") is True
    assert guard.claim("ex_1", owner="b") is True
    with guard.scope("ex_1", owner="c") as won:
        assert won is True


def test_claim_defaults_to_true_when_client_fails() -> None:
    class Broken:
        def set(self, *_args: object, **_kwargs: object) -> bool:
            raise RuntimeError("network down")

    guard = IdempotencyGuard(Broken())
    assert guard.claim("ex_1", owner="a") is True
