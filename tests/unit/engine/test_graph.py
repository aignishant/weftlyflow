"""Tests for :class:`weftlyflow.engine.graph.WorkflowGraph`."""

from __future__ import annotations

import pytest

from tests.unit.engine.conftest import build_workflow, connect, make_node
from weftlyflow.domain.errors import (
    CycleDetectedError,
    InvalidConnectionError,
    WorkflowValidationError,
)
from weftlyflow.domain.workflow import Connection, Node, Workflow
from weftlyflow.engine.graph import WorkflowGraph


def test_topological_order_respects_parent_before_child():
    a = make_node(node_type="weftlyflow.manual_trigger")
    b = make_node(node_type="weftlyflow.no_op")
    c = make_node(node_type="weftlyflow.no_op")
    wf = build_workflow([a, b, c], [connect(a, b), connect(b, c)])
    order = WorkflowGraph(wf).topological_order()
    assert order.index(a.id) < order.index(b.id) < order.index(c.id)


def test_root_ids_are_nodes_without_parents():
    a = make_node(node_type="weftlyflow.manual_trigger")
    b = make_node(node_type="weftlyflow.no_op")
    wf = build_workflow([a, b], [connect(a, b)])
    assert WorkflowGraph(wf).root_ids == (a.id,)


def test_parents_and_children_dedupe_per_node():
    a = make_node(node_type="weftlyflow.manual_trigger")
    b = make_node(node_type="weftlyflow.if")
    c = make_node(node_type="weftlyflow.no_op")
    # two edges from b→c (true + false branches both wired)
    wf = build_workflow(
        [a, b, c],
        [
            connect(a, b),
            connect(b, c, source_port="true"),
            connect(b, c, source_port="false"),
        ],
    )
    g = WorkflowGraph(wf)
    assert g.parents(c.id) == (b.id,)
    assert g.children(b.id) == (c.id,)


def test_duplicate_node_id_raises_validation():
    a = Node(id="node_same", name="A", type="weftlyflow.no_op")
    b = Node(id="node_same", name="B", type="weftlyflow.no_op")
    wf = Workflow(id="wf_dup", project_id="pr_test", name="dup", nodes=[a, b])
    with pytest.raises(WorkflowValidationError):
        WorkflowGraph(wf)


def test_orphan_connection_raises():
    a = make_node(node_type="weftlyflow.no_op")
    bogus = Connection(source_node=a.id, target_node="node_missing")
    wf = Workflow(
        id="wf_orphan",
        project_id="pr_test",
        name="orphan",
        nodes=[a],
        connections=[bogus],
    )
    with pytest.raises(InvalidConnectionError):
        WorkflowGraph(wf)


def test_cycle_raises():
    a = make_node(node_type="weftlyflow.no_op")
    b = make_node(node_type="weftlyflow.no_op")
    wf = build_workflow([a, b], [connect(a, b), connect(b, a)])
    with pytest.raises(CycleDetectedError):
        WorkflowGraph(wf)


def test_outgoing_preserves_declaration_order():
    a = make_node(node_type="weftlyflow.if")
    t = make_node(node_type="weftlyflow.no_op")
    f = make_node(node_type="weftlyflow.no_op")
    wf = build_workflow(
        [a, t, f],
        [connect(a, t, source_port="true"), connect(a, f, source_port="false")],
    )
    edges = WorkflowGraph(wf).outgoing(a.id)
    assert [e.source_port for e in edges] == ["true", "false"]
