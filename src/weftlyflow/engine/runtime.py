"""Per-run mutable state held privately by the executor.

The executor produces one :class:`RunState` per call to ``run()``. It accumulates
:class:`~weftlyflow.domain.execution.NodeRunData` entries as each node
completes and, at the end of the run, materialises a final
:class:`~weftlyflow.domain.execution.Execution` snapshot.

Keeping this state in a dedicated class (rather than a pile of local variables
inside the executor) simplifies testing: the graph walker is a pure function
that takes + returns a ``RunState``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from weftlyflow.domain.execution import (
    Execution,
    NodeRunData,
    RunData,
)
from weftlyflow.engine.constants import STATUS_ERROR, STATUS_SUCCESS

if TYPE_CHECKING:
    from weftlyflow.domain.execution import ExecutionMode, Item
    from weftlyflow.domain.workflow import Workflow


@dataclass(slots=True)
class RunState:
    """Mutable accumulator for one execution of a workflow.

    Attributes:
        workflow: Immutable snapshot of the workflow being executed.
        execution_id: ``ex_<ulid>`` identifier chosen by the executor.
        mode: Trigger mode.
        started_at: UTC timestamp set in ``__post_init__``.
        run_data: Accumulator — one list per node across loop iterations.
        per_node_outputs: ``{node_id: [items_per_port]}`` — latest outputs
            exposed to downstream readiness checks.
        static_data: One shared dict for every node in this run. Seeded in
            ``__post_init__`` from ``workflow.static_data`` (a defensive
            copy — mutation here never touches the caller's workflow
            snapshot). Callers that want cross-run persistence pick this
            up after ``run()`` returns and write it back to the repo.
        failed_node_id: Set when a node raises and the run aborts.
        final_error: Exception object preserved for ``__cause__`` on wrapping.
    """

    workflow: Workflow
    execution_id: str
    mode: ExecutionMode
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    run_data: RunData = field(default_factory=RunData)
    per_node_outputs: dict[str, list[list[Item]]] = field(default_factory=dict)
    static_data: dict[str, Any] = field(init=False)
    failed_node_id: str | None = None
    final_error: BaseException | None = None

    def __post_init__(self) -> None:
        """Seed ``static_data`` from the workflow snapshot, defensively copied."""
        self.static_data = dict(self.workflow.static_data)

    def record(self, node_id: str, run_data: NodeRunData) -> None:
        """Record a completed node run and cache its output for downstream reads."""
        self.run_data.per_node.setdefault(node_id, []).append(run_data)
        if run_data.status != STATUS_ERROR or run_data.items:
            self.per_node_outputs[node_id] = run_data.items

    def mark_failed(self, node_id: str, error: BaseException) -> None:
        """Record a fatal node failure; used by the executor to abort the run."""
        self.failed_node_id = node_id
        self.final_error = error

    def build_execution(self) -> Execution:
        """Materialise the final :class:`Execution` snapshot."""
        status = STATUS_ERROR if self.failed_node_id else STATUS_SUCCESS
        return Execution(
            id=self.execution_id,
            workflow_id=self.workflow.id,
            workflow_snapshot=self.workflow,
            mode=self.mode,
            status=status,
            started_at=self.started_at,
            finished_at=datetime.now(UTC),
            run_data=self.run_data,
        )
