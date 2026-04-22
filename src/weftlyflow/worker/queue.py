"""Abstraction for the workflow-execution queue.

Two implementations exist:

* :class:`CeleryExecutionQueue` — production path. Calls
  ``execute_workflow.apply_async(...)`` on the Celery task defined in
  :mod:`weftlyflow.worker.tasks`.
* :class:`InlineExecutionQueue` — test path. Runs the same core routine
  directly inside the caller's event loop so integration tests can exercise
  the ingress route without spinning up Redis + a Celery worker.

Both implementations accept the same :class:`ExecutionRequest` payload and
therefore stay behaviourally equivalent. Swapping between them happens at
app-boot — the FastAPI lifespan picks one based on env configuration.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from weftlyflow.domain.execution import ExecutionMode
    from weftlyflow.nodes.registry import NodeRegistry

log = structlog.get_logger(__name__)


@dataclass(slots=True, frozen=True)
class ExecutionRequest:
    """Serialisable payload enqueued on the execution queue.

    Attributes:
        execution_id: Pre-allocated ``ex_<ulid>``. The worker looks this up
            on arrival to check for idempotent re-delivery.
        workflow_id: ``wf_<ulid>`` of the workflow to run.
        project_id: Scope boundary; the worker refuses cross-project reads.
        mode: How the run was triggered.
        triggered_by: Free-form identifier (user id, webhook id, schedule id).
        initial_items: List of JSON payloads seeded onto the entry node's
            input port. Empty list yields a single empty :class:`Item`.
    """

    execution_id: str
    workflow_id: str
    project_id: str
    mode: ExecutionMode
    triggered_by: str | None = None
    initial_items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise the request for Celery's JSON serialiser."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionRequest:
        """Rehydrate a request from the shape produced by :meth:`to_dict`."""
        return cls(
            execution_id=data["execution_id"],
            workflow_id=data["workflow_id"],
            project_id=data["project_id"],
            mode=data["mode"],
            triggered_by=data.get("triggered_by"),
            initial_items=list(data.get("initial_items") or []),
        )


class ExecutionQueue(Protocol):
    """Anything that can accept an :class:`ExecutionRequest`."""

    async def enqueue(self, request: ExecutionRequest) -> None:
        """Submit ``request`` for asynchronous execution."""


class InlineExecutionQueue:
    """Test-mode queue — runs the workflow in the current event loop.

    The runner is invoked as a fire-and-forget :class:`asyncio.Task` so the
    ingress handler returns immediately (matching Celery's semantics) while
    the execution completes in the background of the same pytest loop.

    Callers that want to wait for the execution to finish (e.g. integration
    tests after POSTing a webhook) must poll the executions endpoint until
    the status is terminal.
    """

    __slots__ = ("_pending", "_registry", "_session_factory")

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[Any],
        registry: NodeRegistry,
    ) -> None:
        """Bind to a shared session factory + node registry."""
        self._session_factory = session_factory
        self._registry = registry
        self._pending: set[asyncio.Task[None]] = set()

    async def enqueue(self, request: ExecutionRequest) -> None:
        """Kick off a background task that runs the execution inline."""
        # Import here to keep worker/queue.py free of execution-engine imports
        # at module load — keeps the public queue surface cheap.
        from weftlyflow.worker.execution import run_execution_async  # noqa: PLC0415

        async def _run() -> None:
            try:
                await run_execution_async(
                    request,
                    session_factory=self._session_factory,
                    registry=self._registry,
                )
            except Exception as exc:  # pragma: no cover — defensive log
                log.exception(
                    "inline_queue_execution_failed",
                    execution_id=request.execution_id,
                    error=str(exc),
                )

        task = asyncio.create_task(_run(), name=f"execute:{request.execution_id}")
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def drain(self) -> None:
        """Await every outstanding execution. Used by integration tests."""
        if not self._pending:
            return
        await asyncio.gather(*list(self._pending), return_exceptions=True)


class CeleryExecutionQueue:
    """Production queue — hands the payload off to a Celery worker."""

    __slots__ = ("_task",)

    def __init__(self, task: Any) -> None:
        """Bind to a Celery task callable exposing ``apply_async``."""
        self._task = task

    async def enqueue(self, request: ExecutionRequest) -> None:
        """Submit the request to Celery. Returns as soon as the broker accepts it."""
        payload = request.to_dict()
        # ``apply_async`` is sync + may touch the broker; keep the event loop
        # responsive by offloading to the default executor.
        await asyncio.to_thread(
            self._task.apply_async,
            kwargs={"payload": payload},
            task_id=request.execution_id,
        )
