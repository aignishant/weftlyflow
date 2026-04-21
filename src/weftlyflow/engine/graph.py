"""Workflow graph analysis — pure, allocation-cheap DAG queries.

A :class:`WorkflowGraph` is built once from a
:class:`~weftlyflow.domain.workflow.Workflow` and then queried by the executor.
Every operation is O(1) after construction (amortised) or O(V+E) for a full
topological sort; the implementation favours flat lists + integer indexing
over nested dicts to keep the hot-path scheduler allocation-free.

What this module *does not* do:

* evaluate any node,
* call expressions,
* read credentials.

It is strictly graph shape analysis.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from weftlyflow.domain.errors import (
    CycleDetectedError,
    InvalidConnectionError,
    WorkflowValidationError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from weftlyflow.domain.workflow import Connection, Node, Workflow


@dataclass(slots=True, frozen=True)
class OutgoingEdge:
    """One outbound connection indexed by the source port.

    Attributes:
        source_port: Logical name of the output port on the source node.
        source_index: Zero-based index when the port has multiple sockets.
        target_node_id: Downstream node id.
        target_port: Input port on the target node.
        target_index: Index on the target port.
    """

    source_port: str
    source_index: int
    target_node_id: str
    target_port: str
    target_index: int


@dataclass(slots=True, frozen=True)
class IncomingEdge:
    """One inbound connection indexed by the target port.

    Mirrors :class:`OutgoingEdge` from the target's perspective.
    """

    source_node_id: str
    source_port: str
    source_index: int
    target_port: str
    target_index: int


class WorkflowGraph:
    """Read-only DAG view over a :class:`Workflow`.

    The constructor validates structure (orphan connections, cycles, duplicate
    node ids) so the executor can rely on the graph being well-formed.

    Example:
        >>> g = WorkflowGraph(workflow)
        >>> for node_id in g.topological_order():
        ...     ...
    """

    __slots__ = (
        "_incoming",
        "_nodes_by_id",
        "_outgoing",
        "_root_ids",
        "_topo",
        "_workflow",
    )

    def __init__(self, workflow: Workflow) -> None:
        """Build adjacency maps and validate structure.

        Raises:
            WorkflowValidationError: on duplicate node ids.
            InvalidConnectionError: when a connection references a missing node.
            CycleDetectedError: when the graph contains a cycle.
        """
        self._workflow = workflow
        self._nodes_by_id = _build_node_index(workflow)
        self._outgoing, self._incoming = _build_adjacency(workflow, self._nodes_by_id)
        self._topo = _kahn_topological_sort(self._nodes_by_id, self._incoming)
        self._root_ids = tuple(
            node_id
            for node_id in self._topo
            if not self._incoming[node_id]
        )

    @property
    def workflow(self) -> Workflow:
        """Return the underlying workflow snapshot."""
        return self._workflow

    @property
    def root_ids(self) -> tuple[str, ...]:
        """Node ids with no incoming connections (possible start nodes)."""
        return self._root_ids

    def node(self, node_id: str) -> Node:
        """Return the node with ``node_id`` or raise ``KeyError``."""
        return self._nodes_by_id[node_id]

    def has_node(self, node_id: str) -> bool:
        """Return True if ``node_id`` is part of the workflow."""
        return node_id in self._nodes_by_id

    def outgoing(self, node_id: str) -> tuple[OutgoingEdge, ...]:
        """Edges leaving ``node_id`` in declaration order."""
        return self._outgoing[node_id]

    def incoming(self, node_id: str) -> tuple[IncomingEdge, ...]:
        """Edges entering ``node_id`` in declaration order."""
        return self._incoming[node_id]

    def parents(self, node_id: str) -> tuple[str, ...]:
        """Unique parent ids of ``node_id`` preserving first-seen order."""
        seen: dict[str, None] = {}
        for edge in self._incoming[node_id]:
            seen.setdefault(edge.source_node_id)
        return tuple(seen)

    def children(self, node_id: str) -> tuple[str, ...]:
        """Unique child ids of ``node_id`` preserving first-seen order."""
        seen: dict[str, None] = {}
        for edge in self._outgoing[node_id]:
            seen.setdefault(edge.target_node_id)
        return tuple(seen)

    def topological_order(self) -> tuple[str, ...]:
        """Node ids in topological order (parents before children)."""
        return self._topo

    def iter_nodes(self) -> Iterator[Node]:
        """Iterate nodes in topological order."""
        for node_id in self._topo:
            yield self._nodes_by_id[node_id]


def _build_node_index(workflow: Workflow) -> dict[str, Node]:
    index: dict[str, Node] = {}
    for node in workflow.nodes:
        if node.id in index:
            msg = f"duplicate node id in workflow: {node.id!r}"
            raise WorkflowValidationError(msg)
        index[node.id] = node
    return index


def _build_adjacency(
    workflow: Workflow,
    nodes_by_id: dict[str, Node],
) -> tuple[
    dict[str, tuple[OutgoingEdge, ...]],
    dict[str, tuple[IncomingEdge, ...]],
]:
    out_buckets: dict[str, list[OutgoingEdge]] = defaultdict(list)
    in_buckets: dict[str, list[IncomingEdge]] = defaultdict(list)

    for conn in workflow.connections:
        _validate_connection(conn, nodes_by_id)
        out_buckets[conn.source_node].append(
            OutgoingEdge(
                source_port=conn.source_port,
                source_index=conn.source_index,
                target_node_id=conn.target_node,
                target_port=conn.target_port,
                target_index=conn.target_index,
            ),
        )
        in_buckets[conn.target_node].append(
            IncomingEdge(
                source_node_id=conn.source_node,
                source_port=conn.source_port,
                source_index=conn.source_index,
                target_port=conn.target_port,
                target_index=conn.target_index,
            ),
        )

    outgoing = {node_id: tuple(out_buckets.get(node_id, ())) for node_id in nodes_by_id}
    incoming = {node_id: tuple(in_buckets.get(node_id, ())) for node_id in nodes_by_id}
    return outgoing, incoming


def _validate_connection(conn: Connection, nodes_by_id: dict[str, Node]) -> None:
    if conn.source_node not in nodes_by_id:
        msg = f"connection references unknown source node: {conn.source_node!r}"
        raise InvalidConnectionError(msg)
    if conn.target_node not in nodes_by_id:
        msg = f"connection references unknown target node: {conn.target_node!r}"
        raise InvalidConnectionError(msg)


def _kahn_topological_sort(
    nodes_by_id: dict[str, Node],
    incoming: dict[str, tuple[IncomingEdge, ...]],
) -> tuple[str, ...]:
    indegree: dict[str, int] = {
        node_id: len({edge.source_node_id for edge in edges})
        for node_id, edges in incoming.items()
    }
    queue: deque[str] = deque(
        node_id for node_id in nodes_by_id if indegree[node_id] == 0
    )
    order: list[str] = []

    # Build a child-adjacency (unique targets) locally so the sort stays O(V+E).
    children_by_node: dict[str, list[str]] = defaultdict(list)
    seen_edge: set[tuple[str, str]] = set()
    for node_id, edges in incoming.items():
        for edge in edges:
            key = (edge.source_node_id, node_id)
            if key in seen_edge:
                continue
            seen_edge.add(key)
            children_by_node[edge.source_node_id].append(node_id)

    while queue:
        current = queue.popleft()
        order.append(current)
        for child in children_by_node[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(order) != len(nodes_by_id):
        offenders = sorted(nid for nid, deg in indegree.items() if deg > 0)
        msg = f"cycle detected through nodes: {offenders}"
        raise CycleDetectedError(msg)

    return tuple(order)
