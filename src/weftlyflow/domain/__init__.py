"""Pure domain model — dataclasses only, no IO.

This subpackage defines the conceptual vocabulary of Weftlyflow (Workflow, Node,
Connection, Execution, Item, Credential, NodeSpec). It **must not** import from:

- :mod:`weftlyflow.db` (no ORM leakage into the model)
- :mod:`weftlyflow.server` (no FastAPI / Pydantic-in-domain)
- :mod:`weftlyflow.engine` (executors consume the model, not the reverse)

This isolation keeps the model testable without touching a database, lets us
version the wire format independently of the ORM, and prevents the common
"dataclass-that-is-actually-an-ORM-row" anti-pattern.

Cross-reference: weftlyinfo.md §7.
"""

from __future__ import annotations

from weftlyflow.domain.errors import (
    CycleDetectedError,
    InvalidConnectionError,
    NodeExecutionError,
    WeftlyflowError,
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
from weftlyflow.domain.workflow import (
    Connection,
    Node,
    Port,
    RetryPolicy,
    Workflow,
    WorkflowSettings,
)

__all__ = [
    "Connection",
    "CycleDetectedError",
    "Execution",
    "ExecutionMode",
    "ExecutionStatus",
    "InvalidConnectionError",
    "Item",
    "Node",
    "NodeExecutionError",
    "NodeRunData",
    "Port",
    "RetryPolicy",
    "RunData",
    "WeftlyflowError",
    "Workflow",
    "WorkflowSettings",
    "WorkflowValidationError",
    "new_execution_id",
    "new_node_id",
    "new_workflow_id",
]
