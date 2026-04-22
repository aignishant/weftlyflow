"""Sub-workflow runner contract + default in-process implementation.

The engine does not hard-depend on a specific runner (inline worker vs.
Celery dispatch vs. future remote invocation) — the :mod:`function_call`
node only talks to :class:`SubWorkflowRunner`. Callers wire a concrete
implementation onto :class:`~weftlyflow.engine.context.ExecutionContext`
when they want sub-workflow calls to succeed; leaving it unset makes the
node raise a loud, actionable error.

:class:`InlineSubWorkflowRunner` is the canonical in-process impl: it
looks the child workflow up through a pluggable loader callback and runs
it with a fresh :class:`WorkflowExecutor`. Persistence / distribution
are deliberately out of scope — that lives in :mod:`worker`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from weftlyflow.engine.errors import EngineError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from weftlyflow.credentials.resolver import CredentialResolver
    from weftlyflow.domain.execution import Item
    from weftlyflow.domain.workflow import Workflow
    from weftlyflow.nodes.registry import NodeRegistry


class SubWorkflowRunner(Protocol):
    """Execute another workflow in-process and return its final items."""

    async def run(
        self,
        *,
        workflow_id: str,
        items: list[Item],
        parent_execution_id: str,
        project_id: str,
    ) -> list[Item]:
        """Run ``workflow_id`` with ``items`` and return the merged output."""
        ...


class SubWorkflowNotFoundError(EngineError):
    """Raised when the configured loader cannot resolve ``workflow_id``."""


class SubWorkflowProjectMismatchError(EngineError):
    """Raised when the child workflow is not in the parent's project."""


@dataclass(slots=True)
class InlineSubWorkflowRunner:
    """Run child workflows in-process via :class:`WorkflowExecutor`.

    The ``loader`` is the only cross-layer dependency — it bridges from
    ``workflow_id`` to an in-memory :class:`Workflow`. Production wires it
    to the DB repo; tests pass a dict-backed stub.

    Attributes:
        registry: Node registry used by the spawned executor.
        loader: ``async (workflow_id, project_id) -> Workflow | None``.
        credential_resolver: Forwarded to the child executor so child
            nodes can resolve their own credentials.
    """

    registry: NodeRegistry
    loader: Callable[[str, str], Awaitable[Workflow | None]]
    credential_resolver: CredentialResolver | None = None

    async def run(
        self,
        *,
        workflow_id: str,
        items: list[Item],
        parent_execution_id: str,
        project_id: str,
    ) -> list[Item]:
        """Resolve ``workflow_id``, execute it, and return its terminal items."""
        del parent_execution_id  # reserved for tracing / audit, unused today
        child = await self.loader(workflow_id, project_id)
        if child is None:
            msg = (
                f"Sub-workflow {workflow_id!r} not found in project "
                f"{project_id!r}"
            )
            raise SubWorkflowNotFoundError(msg)
        if child.project_id != project_id:
            msg = (
                f"Sub-workflow {workflow_id!r} belongs to project "
                f"{child.project_id!r}, not {project_id!r}"
            )
            raise SubWorkflowProjectMismatchError(msg)

        # Delayed import breaks the cycle: executor imports this module.
        from weftlyflow.engine.executor import WorkflowExecutor  # noqa: PLC0415

        executor = WorkflowExecutor(
            self.registry,
            credential_resolver=self.credential_resolver,
            sub_workflow_runner=self,
        )
        execution = await executor.run(child, initial_items=list(items))
        return _collect_terminal_items(execution)


def _collect_terminal_items(execution: object) -> list[Item]:
    """Flatten the first-output-port items from every terminal node.

    A terminal node has no outgoing connection on the ``main`` port, so
    its items would otherwise have nowhere to go. Unioning those buckets
    gives the child workflow a natural "return value" without needing a
    dedicated Return node.
    """
    from weftlyflow.domain.constants import MAIN_PORT  # noqa: PLC0415
    from weftlyflow.domain.execution import Execution as ExecutionType  # noqa: PLC0415

    assert isinstance(execution, ExecutionType)
    sources_with_main_out = {
        conn.source_node
        for conn in execution.workflow_snapshot.connections
        if conn.source_port == MAIN_PORT
    }
    collected: list[Item] = []
    for node_id, runs in execution.run_data.per_node.items():
        if node_id in sources_with_main_out or not runs:
            continue
        last_run = runs[-1]
        if last_run.items:
            collected.extend(last_run.items[0])
    return collected
