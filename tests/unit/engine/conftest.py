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
    """Return a registry populated with every built-in node.

    One hundred and nineteen built-ins as of the Phase-7
    trigger-chat slice: every Phase-6-core node, eighty-one Tier-2
    integrations, the self-hosted Ollama LLM node, the memory trio
    (``memory_buffer`` / ``memory_window`` / ``memory_summary``), the
    three guardrails (``guard_pii_redact``, ``guard_jailbreak_detect``,
    ``guard_schema_enforce``), the ``text_splitter`` RAG chunker, the
    in-process ``vector_memory`` store, the dependency-free
    ``embed_local`` hashing embedder, the ``chat_respond`` envelope
    shaper, the ``agent_tool_dispatch`` LLM-to-tool fan-out, the
    ``agent_tool_result`` encoder that closes the ReAct loop, and the
    ``trigger_chat`` inbound-chat seed-item unwrapper. The Code node
    (``weftlyflow.code``) is
    deliberately excluded from the default count — it is now gated
    behind ``settings.enable_code_node`` until the subprocess sandbox
    runner lands (see IMPLEMENTATION_BIBLE.md §26 risk #2). Tests that
    need the Code node should register it directly.
    """
    registry = NodeRegistry()
    count = registry.load_builtins()
    assert count == 119, f"expected 119 built-in nodes, got {count}"
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
