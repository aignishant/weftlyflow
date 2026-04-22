"""Worker-level integration for function_call + InlineSubWorkflowRunner.

Boots an in-memory sqlite, writes parent + child workflows, fires the
production :func:`run_execution_async` path, and asserts the persisted
execution reflects the child workflow's output — proving the worker
wires a real DB-backed loader through to the runner.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import weftlyflow.db.entities  # noqa: F401 — register mappers on Base
from tests.unit.engine.conftest import build_workflow, make_node
from weftlyflow.db.base import Base
from weftlyflow.db.repositories.workflow_repo import WorkflowRepository
from weftlyflow.nodes.registry import NodeRegistry
from weftlyflow.worker.execution import run_execution_async
from weftlyflow.worker.queue import ExecutionRequest


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker]:  # type: ignore[type-arg]
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield factory
    finally:
        await engine.dispose()


async def test_run_execution_async_resolves_function_call_through_db_loader(
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
) -> None:
    registry = NodeRegistry()
    registry.load_builtins()

    child_set = make_node(
        node_type="weftlyflow.set",
        parameters={
            "mode": "replace",
            "assignments": [{"name": "from", "value": "child"}],
        },
    )
    child_wf = build_workflow([child_set], [], project_id="pr_test", name="child")

    parent_fn = make_node(
        node_type="weftlyflow.function_call",
        parameters={"workflow_id": child_wf.id, "forward": "main"},
    )
    parent_wf = build_workflow([parent_fn], [], project_id="pr_test", name="parent")

    async with session_factory() as session:
        repo = WorkflowRepository(session)
        await repo.create(child_wf)
        await repo.create(parent_wf)
        await session.commit()

    request = ExecutionRequest(
        execution_id="ex_parent",
        workflow_id=parent_wf.id,
        project_id="pr_test",
        mode="manual",
        initial_items=[{}],
    )
    execution = await run_execution_async(
        request,
        session_factory=session_factory,
        registry=registry,
    )

    assert execution is not None
    assert execution.status == "success"
    fn_run = execution.run_data.per_node[parent_fn.id][-1]
    assert [it.json for it in fn_run.items[0]] == [{"from": "child"}]
