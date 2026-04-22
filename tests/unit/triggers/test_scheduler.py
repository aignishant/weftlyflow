"""Unit tests for scheduler primitives."""

from __future__ import annotations

import pytest

from weftlyflow.triggers.scheduler import InMemoryScheduler, ScheduleSpec


def test_schedule_spec_validates_cron_requires_expression() -> None:
    spec = ScheduleSpec(kind="cron")
    with pytest.raises(ValueError):
        spec.validate()


def test_schedule_spec_validates_interval_requires_seconds() -> None:
    spec = ScheduleSpec(kind="interval")
    with pytest.raises(ValueError):
        spec.validate()


def test_schedule_spec_rejects_unknown_kind() -> None:
    spec = ScheduleSpec(kind="weekly")
    with pytest.raises(ValueError):
        spec.validate()


def test_in_memory_scheduler_add_and_fire() -> None:
    scheduler = InMemoryScheduler()
    calls: list[int] = []

    def callback(payload: int) -> None:
        calls.append(payload)

    scheduler.add_job(
        job_id="j1",
        spec=ScheduleSpec(kind="interval", interval_seconds=60),
        callback=callback,
        args=(42,),
    )
    assert scheduler.has_job("j1")
    scheduler.fire_now("j1")
    assert calls == [42]


def test_in_memory_scheduler_remove_is_silent_when_missing() -> None:
    scheduler = InMemoryScheduler()
    scheduler.remove_job("nonexistent")  # no raise


def test_in_memory_scheduler_lifecycle_flags() -> None:
    scheduler = InMemoryScheduler()
    assert scheduler.started is False
    scheduler.start()
    assert scheduler.started is True
    scheduler.shutdown()
    assert scheduler.started is False
