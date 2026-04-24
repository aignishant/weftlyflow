"""Unit tests for :class:`weftlyflow.triggers.manager.ActiveTriggerManager`.

Backed by in-memory implementations for every dependency — scheduler,
leader lock, execution queue — so the test exercises the activation
bookkeeping without spinning up APScheduler or Redis.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from weftlyflow.db.base import Base
from weftlyflow.db.entities import (  # noqa: F401 — register metadata
    TriggerScheduleEntity,
    WebhookEntity,
)
from weftlyflow.db.repositories.webhook_repo import WebhookRepository
from weftlyflow.domain.ids import new_node_id, new_workflow_id
from weftlyflow.domain.workflow import Node, Workflow
from weftlyflow.triggers.leader import InMemoryLeaderLock
from weftlyflow.triggers.manager import ActiveTriggerManager, is_trigger_type
from weftlyflow.triggers.scheduler import InMemoryScheduler
from weftlyflow.webhooks.registry import WebhookRegistry
from weftlyflow.worker.queue import ExecutionRequest


@dataclass
class _RecordingQueue:
    """Captures every :class:`ExecutionRequest` enqueued during a test."""

    received: list[ExecutionRequest] = field(default_factory=list)

    async def enqueue(self, request: ExecutionRequest) -> None:
        self.received.append(request)


@pytest_asyncio.fixture
async def session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _workflow_with_webhook(*, path: str = "demo/hook") -> Workflow:
    trigger = Node(
        id=new_node_id(),
        name="Webhook",
        type="weftlyflow.webhook_trigger",
        parameters={"path": path, "method": "POST"},
    )
    return Workflow(
        id=new_workflow_id(),
        project_id="pr_demo",
        name="wh-test",
        nodes=[trigger],
        connections=[],
    )


def _workflow_with_schedule(*, interval: int = 60) -> Workflow:
    trigger = Node(
        id=new_node_id(),
        name="Schedule",
        type="weftlyflow.schedule_trigger",
        parameters={"kind": "interval", "interval_seconds": interval},
    )
    return Workflow(
        id=new_workflow_id(),
        project_id="pr_demo",
        name="sched-test",
        nodes=[trigger],
        connections=[],
    )


def _workflow_with_chat_trigger(*, path: str = "chat/room-1") -> Workflow:
    trigger = Node(
        id=new_node_id(),
        name="Chat",
        type="weftlyflow.trigger_chat",
        parameters={"path": path},
    )
    return Workflow(
        id=new_workflow_id(),
        project_id="pr_demo",
        name="chat-test",
        nodes=[trigger],
        connections=[],
    )


def test_is_trigger_type_only_matches_known() -> None:
    assert is_trigger_type("weftlyflow.webhook_trigger")
    assert is_trigger_type("weftlyflow.schedule_trigger")
    assert is_trigger_type("weftlyflow.trigger_chat")
    assert not is_trigger_type("weftlyflow.no_op")


async def test_activate_registers_chat_trigger_on_webhook_registry(session_factory) -> None:  # type: ignore[no-untyped-def]
    registry = WebhookRegistry()
    scheduler = InMemoryScheduler()
    queue = _RecordingQueue()
    leader = InMemoryLeaderLock()
    leader.acquire()
    manager = ActiveTriggerManager(
        session_factory=session_factory,
        registry=registry,
        scheduler=scheduler,
        queue=queue,
        leader=leader,
    )

    wf = _workflow_with_chat_trigger(path="chat/room-1")
    result = await manager.activate(wf)

    assert result.errors == []
    assert result.webhooks_registered == ["chat/room-1"]
    assert registry.match("chat/room-1", "POST") is not None

    async with session_factory() as session:
        rows = await WebhookRepository(session).list_for_workflow(wf.id)
    assert len(rows) == 1


async def test_activate_registers_webhook_entry_and_row(session_factory) -> None:  # type: ignore[no-untyped-def]
    registry = WebhookRegistry()
    scheduler = InMemoryScheduler()
    queue = _RecordingQueue()
    leader = InMemoryLeaderLock()
    leader.acquire()
    manager = ActiveTriggerManager(
        session_factory=session_factory,
        registry=registry,
        scheduler=scheduler,
        queue=queue,
        leader=leader,
    )

    wf = _workflow_with_webhook(path="demo/hook")
    result = await manager.activate(wf)

    assert result.errors == []
    assert result.webhooks_registered == ["demo/hook"]
    assert registry.match("demo/hook", "POST") is not None

    async with session_factory() as session:
        rows = await WebhookRepository(session).list_for_workflow(wf.id)
    assert len(rows) == 1


async def test_deactivate_clears_registrations(session_factory) -> None:  # type: ignore[no-untyped-def]
    registry = WebhookRegistry()
    scheduler = InMemoryScheduler()
    queue = _RecordingQueue()
    leader = InMemoryLeaderLock()
    leader.acquire()
    manager = ActiveTriggerManager(
        session_factory=session_factory,
        registry=registry,
        scheduler=scheduler,
        queue=queue,
        leader=leader,
    )

    wf = _workflow_with_webhook(path="gone/away")
    await manager.activate(wf)
    await manager.deactivate(wf)

    assert registry.match("gone/away", "POST") is None
    async with session_factory() as session:
        remaining = await WebhookRepository(session).list_for_workflow(wf.id)
    assert remaining == []


async def test_activate_with_schedule_fires_queue_on_tick(session_factory) -> None:  # type: ignore[no-untyped-def]
    registry = WebhookRegistry()
    scheduler = InMemoryScheduler()
    queue = _RecordingQueue()
    leader = InMemoryLeaderLock()
    leader.acquire()
    manager = ActiveTriggerManager(
        session_factory=session_factory,
        registry=registry,
        scheduler=scheduler,
        queue=queue,
        leader=leader,
    )

    wf = _workflow_with_schedule()
    result = await manager.activate(wf)
    assert len(result.schedules_registered) == 1

    job_id = result.schedules_registered[0]
    assert scheduler.has_job(job_id)

    # The callback is sync + uses asyncio.run internally; fire it and wait.
    scheduler.fire_now(job_id)
    # Give the event loop a chance to drain the task spawned by _schedule_on_loop.
    await asyncio.sleep(0.05)

    assert len(queue.received) == 1
    enqueued = queue.received[0]
    assert enqueued.workflow_id == wf.id
    assert enqueued.mode == "trigger"


async def test_schedule_does_not_fire_when_not_leader(session_factory) -> None:  # type: ignore[no-untyped-def]
    registry = WebhookRegistry()
    scheduler = InMemoryScheduler()
    queue = _RecordingQueue()
    leader = InMemoryLeaderLock()
    # Intentionally do NOT acquire — we simulate a follower instance.
    manager = ActiveTriggerManager(
        session_factory=session_factory,
        registry=registry,
        scheduler=scheduler,
        queue=queue,
        leader=leader,
    )

    wf = _workflow_with_schedule()
    result = await manager.activate(wf)
    job_id = result.schedules_registered[0]

    scheduler.fire_now(job_id)
    await asyncio.sleep(0.02)

    assert queue.received == []


async def test_warm_up_rehydrates_registry(session_factory) -> None:  # type: ignore[no-untyped-def]
    registry_a = WebhookRegistry()
    scheduler_a = InMemoryScheduler()
    queue_a = _RecordingQueue()
    leader = InMemoryLeaderLock()
    leader.acquire()
    manager_a = ActiveTriggerManager(
        session_factory=session_factory,
        registry=registry_a,
        scheduler=scheduler_a,
        queue=queue_a,
        leader=leader,
    )
    wf = _workflow_with_webhook(path="persist/me")
    await manager_a.activate(wf)

    # New instance — bare registries, same DB.
    registry_b = WebhookRegistry()
    scheduler_b = InMemoryScheduler()
    manager_b = ActiveTriggerManager(
        session_factory=session_factory,
        registry=registry_b,
        scheduler=scheduler_b,
        queue=queue_a,
        leader=leader,
    )
    count = await manager_b.warm_up()
    assert count == 1
    assert registry_b.match("persist/me", "POST") is not None


async def test_activate_rejects_invalid_schedule(session_factory) -> None:  # type: ignore[no-untyped-def]
    registry = WebhookRegistry()
    scheduler = InMemoryScheduler()
    queue = _RecordingQueue()
    leader = InMemoryLeaderLock()
    leader.acquire()
    manager = ActiveTriggerManager(
        session_factory=session_factory,
        registry=registry,
        scheduler=scheduler,
        queue=queue,
        leader=leader,
    )

    bad_trigger = Node(
        id=new_node_id(),
        name="Bad",
        type="weftlyflow.schedule_trigger",
        # cron without expression — caught by ScheduleSpec.validate.
        parameters={"kind": "cron"},
    )
    wf = Workflow(
        id=new_workflow_id(),
        project_id="pr_demo",
        name="bad",
        nodes=[bad_trigger],
        connections=[],
    )
    result = await manager.activate(wf)
    assert result.errors
    assert result.schedules_registered == []


# Silence a ruff warning about the fixture parameter type.
pytestmark = pytest.mark.unit
