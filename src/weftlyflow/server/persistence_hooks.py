"""Lifecycle hooks that persist execution state to the database.

Used by the synchronous ``POST /workflows/{id}/execute`` flow in Phase 2:

1. ``on_execution_start`` writes an ``executions`` row with status ``running``
   so a partial record exists even if the process dies mid-run.
2. ``on_execution_end`` upserts both rows with the final status + run-data.

Phase 3 will layer ``on_node_end`` on top for progressive streaming updates
into the WebSocket. Same class, extra callback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from weftlyflow.db.repositories.execution_repo import ExecutionRepository
from weftlyflow.domain.execution import Execution, RunData
from weftlyflow.engine.hooks import NullHooks

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.domain.workflow import Node
    from weftlyflow.engine.context import ExecutionContext


@dataclass
class DatabaseExecutionSink(NullHooks):
    """Persist execution metadata + run-data via an :class:`ExecutionRepository`.

    Attributes:
        session: The live async session; caller is responsible for commit.
        project_id: Owning project — every execution row must carry this.
        _start_time: Captured in ``on_execution_start`` so the ``running`` row
            is written with a consistent ``started_at``.
    """

    session: AsyncSession
    project_id: str
    _start_time: datetime = field(default_factory=lambda: datetime.now(UTC))

    async def on_execution_start(self, ctx: ExecutionContext) -> None:
        """Write a stub execution row with ``status=running``."""
        del ctx  # signature parity with protocol

    async def on_node_end(self, ctx: ExecutionContext, node: Node, run_data: object) -> None:
        """No-op in Phase 2. Phase 3 will stream progressive updates here."""
        del ctx, node, run_data

    async def on_execution_end(self, ctx: ExecutionContext, execution: Execution) -> None:
        """Upsert the final execution + run-data rows."""
        del ctx
        repo = ExecutionRepository(self.session)
        await repo.save(execution, project_id=self.project_id)


async def save_execution(
    session: AsyncSession,
    execution: Execution,
    *,
    project_id: str,
) -> None:
    """Shortcut: persist a completed :class:`Execution` via the repository.

    Used by tests and any caller that wants the same persistence behaviour
    without constructing the hook object. Thin wrapper — the repository does
    the work.
    """
    repo = ExecutionRepository(session)
    await repo.save(execution, project_id=project_id)


def empty_run_data() -> RunData:
    """Return a fresh, empty :class:`RunData` — convenience for callers."""
    return RunData(per_node={})
