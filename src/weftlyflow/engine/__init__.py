"""Execution engine — the heart of Weftlyflow.

The engine takes a :class:`weftlyflow.domain.workflow.Workflow` plus initial items
and produces a :class:`weftlyflow.domain.execution.Execution`. It is framework-free:
no FastAPI, no SQLAlchemy, no Celery imports. This makes the engine unit-testable
with nothing but the domain package.

Modules (added across Phases 1–3):
    executor : :class:`WorkflowExecutor` — the main loop.
    graph    : DAG analysis (parents, children, topo order, cycle detection).
    context  : :class:`ExecutionContext` passed to every node.
    hooks    : :class:`LifecycleHooks` — observability + DB-write callbacks.
    retry    : per-node retry policy application.
    pin_data : short-circuit with pinned outputs (dev only).
    cancel   : cooperative cancellation.
    partial  : resume-from-failed-node support.

See IMPLEMENTATION_BIBLE.md §8.
"""

from __future__ import annotations
