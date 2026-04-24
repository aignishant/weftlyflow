"""Repository x ExecutionDataStore integration.

Round-trips a full :class:`Execution` through ``ExecutionRepository`` with
each store backend and asserts the entity rows match the expected shape:
``db`` keeps payload inline, ``fs`` clears the JSON columns and writes the
blob to disk.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from weftlyflow.db.base import Base
from weftlyflow.db.entities import (  # noqa: F401 — register tables
    ExecutionDataEntity,
    ExecutionEntity,
)
from weftlyflow.db.execution_storage import (
    STORAGE_KIND_DB,
    STORAGE_KIND_FS,
    DbExecutionDataStore,
    FilesystemExecutionDataStore,
)
from weftlyflow.db.repositories.execution_repo import ExecutionRepository
from weftlyflow.domain.execution import Execution, Item, NodeRunData, RunData
from weftlyflow.domain.workflow import Workflow, WorkflowSettings

pytestmark = pytest.mark.unit


def _build_execution() -> Execution:
    wf = Workflow(
        id="wf_test",
        project_id="proj_test",
        name="round-trip",
        nodes=[],
        connections=[],
        settings=WorkflowSettings(),
        static_data={},
        pin_data={},
        active=False,
        archived=False,
        tags=[],
        version_id=None,
    )
    rd = RunData(
        per_node={
            "n1": [
                NodeRunData(
                    items=[[Item(json={"hello": "world"}, binary={}, paired_item=[])]],
                    execution_time_ms=4,
                    started_at=datetime.now(UTC),
                    status="success",
                    error=None,
                ),
            ],
        },
    )
    return Execution(
        id="exec_abc",
        workflow_id="wf_test",
        workflow_snapshot=wf,
        mode="manual",
        status="success",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        wait_till=None,
        run_data=rd,
        data_storage="db",
        triggered_by="admin",
    )


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    yield factory
    await engine.dispose()


async def test_db_backend_round_trip(session_factory) -> None:
    execution = _build_execution()

    async with session_factory() as session:
        repo = ExecutionRepository(session, data_store=DbExecutionDataStore())
        await repo.save(execution, project_id="proj_test")
        await session.commit()

    async with session_factory() as session:
        data_row = await session.get(ExecutionDataEntity, execution.id)
        assert data_row is not None
        assert data_row.storage_kind == STORAGE_KIND_DB
        assert data_row.external_ref is None
        assert data_row.workflow_snapshot != {}
        assert data_row.run_data != {}

        repo = ExecutionRepository(session, data_store=DbExecutionDataStore())
        loaded = await repo.get(execution.id, project_id="proj_test")
        assert loaded is not None
        assert loaded.id == execution.id
        assert "n1" in loaded.run_data.per_node


async def test_fs_backend_round_trip(
    session_factory,
    tmp_path: Path,
) -> None:
    execution = _build_execution()
    store = FilesystemExecutionDataStore(base_path=tmp_path)

    async with session_factory() as session:
        repo = ExecutionRepository(session, data_store=store)
        await repo.save(execution, project_id="proj_test")
        await session.commit()

    async with session_factory() as session:
        data_row = await session.get(ExecutionDataEntity, execution.id)
        assert data_row is not None
        assert data_row.storage_kind == STORAGE_KIND_FS
        assert data_row.external_ref is not None
        # JSON columns are empty — the payload lives on disk.
        assert data_row.workflow_snapshot == {}
        assert data_row.run_data == {}
        assert (tmp_path / data_row.external_ref).is_file()

        repo = ExecutionRepository(session, data_store=store)
        loaded = await repo.get(execution.id, project_id="proj_test")
        assert loaded is not None
        assert loaded.data_storage == STORAGE_KIND_FS
        assert "n1" in loaded.run_data.per_node
        assert loaded.run_data.per_node["n1"][0].items[0][0].json == {"hello": "world"}


async def test_fs_backend_overwrite_updates_payload(
    session_factory,
    tmp_path: Path,
) -> None:
    store = FilesystemExecutionDataStore(base_path=tmp_path)
    execution = _build_execution()

    async with session_factory() as session:
        repo = ExecutionRepository(session, data_store=store)
        await repo.save(execution, project_id="proj_test")
        # Second save mutates run_data — ensure the on-disk file is replaced.
        execution2 = replace(execution, run_data=RunData(per_node={"n1": []}))
        await repo.save(execution2, project_id="proj_test")
        await session.commit()

    async with session_factory() as session:
        repo = ExecutionRepository(session, data_store=store)
        loaded = await repo.get(execution.id, project_id="proj_test")

    assert loaded is not None
    assert loaded.run_data.per_node == {"n1": []}
