"""Execution engine — the heart of Weftlyflow.

The engine takes a :class:`weftlyflow.domain.workflow.Workflow` plus initial items
and produces a :class:`weftlyflow.domain.execution.Execution`. It is framework-free:
no FastAPI, no SQLAlchemy, no Celery imports. This makes the engine unit-testable
with nothing but the domain package plus a :class:`NodeRegistry`.

Public surface:
    WorkflowExecutor : run a workflow end-to-end.
    WorkflowGraph    : DAG analysis (parents, children, topo order).
    ExecutionContext : the object every node receives.
    LifecycleHooks   : protocol for observability callbacks.
    NullHooks        : no-op default implementation of the hooks protocol.
    RunState         : mutable accumulator (exposed for advanced use cases).

Engine errors (``EngineError``, ``NodeTypeNotFoundError``, ...) live in
:mod:`weftlyflow.engine.errors`.

See weftlyinfo.md §8.
"""

from __future__ import annotations

from weftlyflow.engine.context import ExecutionContext
from weftlyflow.engine.errors import (
    EngineError,
    NodeTypeNotFoundError,
    OutputPortIndexError,
    UnreachableNodeError,
)
from weftlyflow.engine.executor import WorkflowExecutor
from weftlyflow.engine.graph import IncomingEdge, OutgoingEdge, WorkflowGraph
from weftlyflow.engine.hooks import LifecycleHooks, NullHooks
from weftlyflow.engine.runtime import RunState

__all__ = [
    "EngineError",
    "ExecutionContext",
    "IncomingEdge",
    "LifecycleHooks",
    "NodeTypeNotFoundError",
    "NullHooks",
    "OutgoingEdge",
    "OutputPortIndexError",
    "RunState",
    "UnreachableNodeError",
    "WorkflowExecutor",
    "WorkflowGraph",
]
