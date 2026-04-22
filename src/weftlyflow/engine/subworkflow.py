"""Sub-workflow runner contract used by the :mod:`function_call` node.

The engine does not hard-depend on a specific runner (inline worker vs.
Celery dispatch vs. future remote invocation) — the node only talks to
this :class:`SubWorkflowRunner` protocol. Callers wire a concrete
implementation onto :class:`~weftlyflow.engine.context.ExecutionContext`
when they want sub-workflow calls to succeed; leaving it unset makes the
node raise a loud, actionable error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from weftlyflow.domain.execution import Item


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
