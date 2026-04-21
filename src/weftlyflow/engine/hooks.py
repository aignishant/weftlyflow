"""Lifecycle hooks — observability + side-effect callbacks for executions.

Hooks are how the engine talks to the outside world without taking a hard
dependency on FastAPI, structlog, or the database. An implementation plugs
into:

* the API's WebSocket stream (Phase 3),
* the execution-persistence writer (Phase 2),
* Prometheus metrics (Phase 8),
* OpenTelemetry spans (Phase 8).

Every hook method is async and returns ``None``. The default
:class:`NullHooks` does nothing — the engine uses it when the caller does not
provide one, so the core loop never has to branch on ``hooks is None``.

Example:
    class LogHooks:
        async def on_node_start(self, ctx, node):
            log.info("node_start", node=node.id)

        # ...other methods left to NullHooks via Protocol duck typing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from weftlyflow.domain.execution import Execution, NodeRunData
    from weftlyflow.domain.workflow import Node
    from weftlyflow.engine.context import ExecutionContext


@runtime_checkable
class LifecycleHooks(Protocol):
    """Protocol describing the callbacks the executor invokes during a run.

    Implementations may override any subset; unimplemented methods fall back
    to the no-op bodies in :class:`NullHooks` via duck typing.
    """

    async def on_execution_start(self, ctx: ExecutionContext) -> None:
        """Invoked exactly once before any node runs."""

    async def on_execution_end(self, ctx: ExecutionContext, execution: Execution) -> None:
        """Invoked exactly once after the run reaches a terminal state."""

    async def on_node_start(self, ctx: ExecutionContext, node: Node) -> None:
        """Invoked immediately before a node's ``execute`` is called."""

    async def on_node_end(
        self,
        ctx: ExecutionContext,
        node: Node,
        run_data: NodeRunData,
    ) -> None:
        """Invoked after a node returns (success, disabled, or continue-on-fail error)."""

    async def on_node_error(
        self,
        ctx: ExecutionContext,
        node: Node,
        error: BaseException,
    ) -> None:
        """Invoked when a node raises and ``continue_on_fail`` is False."""


class NullHooks:
    """Default implementation — every callback is a no-op.

    Concrete hook implementations inherit from this so they only have to
    override the callbacks they care about.
    """

    async def on_execution_start(self, ctx: ExecutionContext) -> None:
        """No-op default."""

    async def on_execution_end(self, ctx: ExecutionContext, execution: Execution) -> None:
        """No-op default."""

    async def on_node_start(self, ctx: ExecutionContext, node: Node) -> None:
        """No-op default."""

    async def on_node_end(
        self,
        ctx: ExecutionContext,
        node: Node,
        run_data: NodeRunData,
    ) -> None:
        """No-op default."""

    async def on_node_error(
        self,
        ctx: ExecutionContext,
        node: Node,
        error: BaseException,
    ) -> None:
        """No-op default."""
