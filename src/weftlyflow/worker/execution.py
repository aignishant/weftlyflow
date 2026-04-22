"""Core routine that executes a queued workflow + persists the result.

Both the Celery task and the inline-test queue funnel into this function.
It is deliberately free of Celery/asyncio-policy concerns:

* :func:`run_execution_async` is the primary implementation, used by the
  in-process queue and any async caller.
* :func:`run_execution_sync` wraps it with :func:`asyncio.run` so Celery
  tasks — which are synchronous by contract — can invoke the same logic
  without leaking event-loop details into the task body.

On arrival the runner:

1. Opens a fresh async session from the provided factory.
2. Loads the workflow (404 → log + abort; no execution row written).
3. Seeds the executor with ``request.initial_items`` and runs it.
4. Rewrites the execution id so callers that reserved one upstream see the
   run persisted under their chosen id.
5. Persists the completed execution through the existing repository path.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import structlog

from weftlyflow.domain.execution import Item
from weftlyflow.engine.executor import WorkflowExecutor
from weftlyflow.engine.subworkflow import InlineSubWorkflowRunner

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from weftlyflow.credentials.resolver import CredentialResolver
    from weftlyflow.domain.execution import Execution
    from weftlyflow.domain.workflow import Workflow
    from weftlyflow.nodes.registry import NodeRegistry
    from weftlyflow.worker.queue import ExecutionRequest

log = structlog.get_logger(__name__)


async def run_execution_async(
    request: ExecutionRequest,
    *,
    session_factory: async_sessionmaker[Any],
    registry: NodeRegistry,
    credential_resolver: CredentialResolver | None = None,
) -> Execution | None:
    """Run the workflow referenced by ``request`` and persist the result.

    Returns the :class:`Execution` on success, or ``None`` when the workflow
    could not be resolved (logs a warning in that case).
    """
    from weftlyflow.db.repositories.execution_repo import (  # noqa: PLC0415
        ExecutionRepository,
    )
    from weftlyflow.db.repositories.workflow_repo import (  # noqa: PLC0415
        WorkflowRepository,
    )

    bound_log = log.bind(
        execution_id=request.execution_id,
        workflow_id=request.workflow_id,
        project_id=request.project_id,
        mode=request.mode,
    )

    async with session_factory() as session:
        workflow = await WorkflowRepository(session).get(
            request.workflow_id, project_id=request.project_id,
        )
        if workflow is None:
            bound_log.warning("execute_workflow_not_found")
            return None

        items = [Item(json=dict(payload)) for payload in request.initial_items] or [Item()]
        bound_log.info("execute_workflow_start", items=len(items))

        sub_workflow_runner = InlineSubWorkflowRunner(
            registry=registry,
            loader=_build_workflow_loader(session_factory),
            credential_resolver=credential_resolver,
        )
        executor = WorkflowExecutor(
            registry,
            credential_resolver=credential_resolver,
            sub_workflow_runner=sub_workflow_runner,
        )
        execution = await executor.run(
            workflow,
            initial_items=items,
            mode=request.mode,
            execution_id=request.execution_id,
        )
        persisted = replace(
            execution,
            triggered_by=request.triggered_by,
        )
        await ExecutionRepository(session).save(persisted, project_id=request.project_id)
        await session.commit()

        bound_log.info(
            "execute_workflow_finish",
            status=persisted.status,
            duration_ms=_duration_ms(persisted),
        )
        return persisted


def run_execution_sync(
    request: ExecutionRequest,
    *,
    session_factory: async_sessionmaker[Any],
    registry: NodeRegistry,
    credential_resolver: CredentialResolver | None = None,
) -> Execution | None:
    """Blocking wrapper around :func:`run_execution_async`.

    Exists so Celery tasks (which are sync callables) can invoke the async
    engine without every task body re-implementing the event-loop dance.
    """
    return asyncio.run(
        run_execution_async(
            request,
            session_factory=session_factory,
            registry=registry,
            credential_resolver=credential_resolver,
        ),
    )


def _build_workflow_loader(
    session_factory: async_sessionmaker[Any],
) -> Callable[[str, str], Awaitable[Workflow | None]]:
    """Return a loader that resolves workflows through a fresh DB session.

    Each child lookup runs in its own read-only session so parent
    executions don't hold a connection open for the duration of the run.
    """
    from weftlyflow.db.repositories.workflow_repo import (  # noqa: PLC0415
        WorkflowRepository,
    )

    async def load(workflow_id: str, project_id: str) -> Workflow | None:
        async with session_factory() as session:
            return await WorkflowRepository(session).get(
                workflow_id, project_id=project_id,
            )

    return load


def _duration_ms(execution: Execution) -> int:
    if execution.finished_at is None:
        return 0
    delta = execution.finished_at - execution.started_at
    return int(delta.total_seconds() * 1000)
