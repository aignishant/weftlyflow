"""ExecutionContext — the single object every node receives during execution.

Keeping nodes dependent on one well-defined context (rather than a grab-bag of
kwargs) makes the node contract stable across phases: Phase 4 will extend the
context with credential resolution and expression evaluation, but the node
signature stays the same.

Only the fields nodes *actually need* are exposed here. The executor holds a
larger :class:`~weftlyflow.engine.runtime.RunState` privately and hands nodes a
narrow view via this class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from weftlyflow.domain.constants import MAIN_PORT

if TYPE_CHECKING:
    from weftlyflow.domain.execution import ExecutionMode, Item
    from weftlyflow.domain.workflow import Node, Workflow
    from weftlyflow.engine.hooks import LifecycleHooks


@dataclass(slots=True)
class ExecutionContext:
    """Per-node view of the current execution.

    Attributes:
        workflow: The immutable workflow snapshot being executed.
        execution_id: The ``ex_<ulid>`` identifier for this run.
        mode: How the execution was triggered.
        node: The node currently being executed.
        inputs: ``{port_name: [items]}`` — the inputs presented to this node.
        static_data: Mutable per-workflow key-value store (persisted across runs
            in Phase 2; in-memory only for Phase 1).
        hooks: Lifecycle hooks (defaults to a null implementation).
        canceled: Cooperative cancellation flag; nodes that do long work should
            check this periodically and bail out.
    """

    workflow: Workflow
    execution_id: str
    mode: ExecutionMode
    node: Node
    inputs: dict[str, list[Item]] = field(default_factory=dict)
    static_data: dict[str, Any] = field(default_factory=dict)
    hooks: LifecycleHooks | None = None
    canceled: bool = False

    def param(self, name: str, default: Any = None) -> Any:
        """Return the node parameter ``name`` or ``default`` if missing.

        Centralises parameter access so Phase 4 can inject expression
        evaluation without changing every node.
        """
        return self.node.parameters.get(name, default)

    def get_input(self, port: str = MAIN_PORT) -> list[Item]:
        """Return the items on input port ``port`` (empty list if unconnected)."""
        return self.inputs.get(port, [])
