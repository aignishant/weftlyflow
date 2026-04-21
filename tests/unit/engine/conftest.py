"""Shared fixtures for engine tests.

Exposes a ``loaded_registry`` fixture that auto-discovers every built-in node,
and small builder helpers to keep individual tests focused on *what* they
assert rather than *how* to assemble a workflow.
"""

from __future__ import annotations

from typing import Any

import pytest

from weftlyflow.domain.execution import Item
from weftlyflow.domain.ids import new_node_id, new_workflow_id
from weftlyflow.domain.workflow import Connection, Node, Workflow
from weftlyflow.nodes.registry import NodeRegistry


@pytest.fixture
def loaded_registry() -> NodeRegistry:
    """Return a registry populated with every built-in core node."""
    registry = NodeRegistry()
    count = registry.load_builtins()
    assert count == 5, f"expected 5 built-in nodes, got {count}"
    return registry


@pytest.fixture
def empty_registry() -> NodeRegistry:
    """Return an empty registry — caller registers what they need."""
    return NodeRegistry()


def make_node(
    *,
    node_type: str,
    name: str | None = None,
    parameters: dict[str, Any] | None = None,
    disabled: bool = False,
    continue_on_fail: bool = False,
    node_id: str | None = None,
) -> Node:
    """Build a :class:`Node` with sane defaults for tests."""
    return Node(
        id=node_id or new_node_id(),
        name=name or node_type,
        type=node_type,
        parameters=parameters or {},
        disabled=disabled,
        continue_on_fail=continue_on_fail,
    )


def connect(
    source: Node,
    target: Node,
    *,
    source_port: str = "main",
    source_index: int = 0,
    target_port: str = "main",
) -> Connection:
    """Build a :class:`Connection` between two nodes."""
    return Connection(
        source_node=source.id,
        target_node=target.id,
        source_port=source_port,
        source_index=source_index,
        target_port=target_port,
    )


def build_workflow(
    nodes: list[Node],
    connections: list[Connection],
    *,
    project_id: str = "pr_test",
    name: str = "test",
) -> Workflow:
    """Assemble a :class:`Workflow` from nodes + connections."""
    return Workflow(
        id=new_workflow_id(),
        project_id=project_id,
        name=name,
        nodes=nodes,
        connections=connections,
    )


def one_item(payload: dict[str, Any] | None = None) -> list[Item]:
    """Convenience: single-item seed list."""
    return [Item(json=dict(payload or {}))]
