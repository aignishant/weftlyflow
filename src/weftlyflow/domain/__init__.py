"""Pure domain model — dataclasses only, no IO.

This subpackage defines the conceptual vocabulary of Weftlyflow (Workflow, Node,
Connection, Execution, Item, Credential, NodeSpec). It **must not** import from:

- :mod:`weftlyflow.db` (no ORM leakage into the model)
- :mod:`weftlyflow.server` (no FastAPI / Pydantic-in-domain)
- :mod:`weftlyflow.engine` (executors consume the model, not the reverse)

This isolation keeps the model testable without touching a database, lets us
version the wire format independently of the ORM, and prevents the common
"dataclass-that-is-actually-an-ORM-row" anti-pattern.

Cross-reference: IMPLEMENTATION_BIBLE.md §7.
"""

from __future__ import annotations

from weftlyflow.domain.errors import (
    CycleDetectedError,
    InvalidConnectionError,
    WeftlyflowError,
    NodeExecutionError,
    WorkflowValidationError,
)
from weftlyflow.domain.execution import (
    Execution,
    ExecutionMode,
    ExecutionStatus,
    Item,
    NodeRunData,
    RunData,
)
from weftlyflow.domain.ids import new_execution_id, new_node_id, new_workflow_id
from weftlyflow.domain.workflow import Connection, Node, Port, RetryPolicy, Workflow, WorkflowSettings

__all__ = [
    # errors
    "WeftlyflowError",
    "WorkflowValidationError",
    "InvalidConnectionError",
    "CycleDetectedError",
    "NodeExecutionError",
    # workflow
    "Workflow",
    "WorkflowSettings",
    "Node",
    "Connection",
    "Port",
    "RetryPolicy",
    # execution
    "Execution",
    "ExecutionMode",
    "ExecutionStatus",
    "Item",
    "RunData",
    "NodeRunData",
    # ids
    "new_workflow_id",
    "new_node_id",
    "new_execution_id",
]
