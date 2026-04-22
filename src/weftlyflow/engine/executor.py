"""WorkflowExecutor — the core run loop.

The executor walks a validated :class:`WorkflowGraph` in readiness order: a
node becomes eligible to run once every one of its unique parents has produced
output (or was disabled / pinned). This differs from the simplified stack in
the bible's §8.1 only in how it handles fan-in — a node with two parents waits
for both before firing, instead of running once per parent.

Responsibilities:

* resolve each :class:`Node` to a registered :class:`BaseNode` implementation,
* build the per-node :class:`ExecutionContext` with the inputs for that node,
* invoke the node (respecting ``disabled``, ``pin_data``, ``continue_on_fail``),
* capture a :class:`NodeRunData` entry in the :class:`RunState`,
* route each output port's items to downstream nodes,
* surface lifecycle events to the configured :class:`LifecycleHooks`.

The executor does **not**:

* evaluate expressions (Phase 4),
* resolve credentials (Phase 4),
* persist anything (Phase 2 — persistence is a hook).
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from weftlyflow.domain.constants import MAIN_PORT
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item, NodeError, NodeRunData
from weftlyflow.domain.ids import new_execution_id
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.constants import (
    STATUS_DISABLED,
    STATUS_ERROR,
    STATUS_SUCCESS,
)
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.engine.errors import NodeTypeNotFoundError
from weftlyflow.engine.graph import WorkflowGraph
from weftlyflow.engine.hooks import NullHooks
from weftlyflow.engine.runtime import RunState
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.credentials.resolver import CredentialResolver
    from weftlyflow.domain.execution import Execution, ExecutionMode
    from weftlyflow.domain.workflow import Workflow
    from weftlyflow.engine.hooks import LifecycleHooks
    from weftlyflow.engine.subworkflow import SubWorkflowRunner
    from weftlyflow.nodes.registry import NodeRegistry


class WorkflowExecutor:
    """Run a :class:`Workflow` from start to terminal state.

    One executor instance is safe to reuse across runs; each call to
    :meth:`run` builds its own :class:`RunState`.

    Example:
        >>> executor = WorkflowExecutor(registry)
        >>> execution = await executor.run(workflow, initial_items=[Item()])
        >>> execution.status
        'success'
    """

    __slots__ = (
        "_credential_resolver",
        "_hooks",
        "_registry",
        "_sub_workflow_runner",
    )

    def __init__(
        self,
        registry: NodeRegistry,
        *,
        hooks: LifecycleHooks | None = None,
        credential_resolver: CredentialResolver | None = None,
        sub_workflow_runner: SubWorkflowRunner | None = None,
    ) -> None:
        """Bind the registry used for node lookup and the optional hooks."""
        self._registry = registry
        self._hooks: LifecycleHooks = hooks or NullHooks()
        self._credential_resolver = credential_resolver
        self._sub_workflow_runner = sub_workflow_runner

    async def run(
        self,
        workflow: Workflow,
        *,
        initial_items: list[Item] | None = None,
        mode: ExecutionMode = "manual",
        execution_id: str | None = None,
    ) -> Execution:
        """Execute ``workflow`` and return the resulting :class:`Execution`.

        Args:
            workflow: The workflow to run. It is treated as immutable.
            initial_items: Items fed into each root node's ``main`` port.
                Defaults to a single empty :class:`Item`.
            mode: How this run was triggered. Persisted on the execution row.
            execution_id: Override for the generated id (tests, re-runs).

        Returns:
            The final :class:`Execution` record including per-node run data.
        """
        graph = WorkflowGraph(workflow)
        state = RunState(
            workflow=workflow,
            execution_id=execution_id or new_execution_id(),
            mode=mode,
        )
        seed_items = initial_items if initial_items is not None else [Item()]

        inputs_by_node = _seed_inputs_for_roots(graph, seed_items)
        pending = _compute_initial_pending(graph)
        ready_queue: deque[str] = deque(graph.root_ids)

        await self._hooks.on_execution_start(
            ExecutionContext(
                workflow=workflow,
                execution_id=state.execution_id,
                mode=state.mode,
                node=workflow.nodes[0] if workflow.nodes else _synthetic_node(),
                hooks=self._hooks,
                credential_resolver=self._credential_resolver,
                sub_workflow_runner=self._sub_workflow_runner,
            ),
        )

        while ready_queue and state.failed_node_id is None:
            node_id = ready_queue.popleft()
            node = graph.node(node_id)
            ctx = ExecutionContext(
                workflow=workflow,
                execution_id=state.execution_id,
                mode=state.mode,
                node=node,
                inputs=inputs_by_node.get(node_id, {}),
                hooks=self._hooks,
                credential_resolver=self._credential_resolver,
                sub_workflow_runner=self._sub_workflow_runner,
            )

            await self._hooks.on_node_start(ctx, node)
            run_data = await self._run_one(node, ctx, state)
            state.record(node_id, run_data)
            await self._hooks.on_node_end(ctx, node, run_data)

            if run_data.status == STATUS_ERROR and not node.continue_on_fail:
                # _run_one has already marked state failed; do not propagate.
                continue

            _propagate_outputs(
                graph=graph,
                source_id=node_id,
                outputs=run_data.items,
                inputs_by_node=inputs_by_node,
            )
            _advance_readiness(
                graph=graph,
                just_finished=node_id,
                pending=pending,
                ready_queue=ready_queue,
            )

        execution = state.build_execution()
        await self._hooks.on_execution_end(_exit_context(workflow, state, self._hooks), execution)
        return execution

    async def _run_one(
        self,
        node: Node,
        ctx: ExecutionContext,
        state: RunState,
    ) -> NodeRunData:
        """Execute one node and build its :class:`NodeRunData` entry."""
        started_at = datetime.now(UTC)

        if node.disabled:
            return _disabled_run_data(ctx, started_at)

        pinned = ctx.workflow.pin_data.get(node.id)
        if pinned is not None:
            items = [[Item(json=payload) for payload in pinned]]
            return _elapsed(started_at, items, STATUS_SUCCESS)

        try:
            implementation = self._resolve_node(node)
            output = await implementation.execute(ctx, ctx.get_input(MAIN_PORT))
        except Exception as exc:
            return await self._handle_node_exception(node, ctx, exc, state, started_at)

        return _elapsed(started_at, output, STATUS_SUCCESS)

    def _resolve_node(self, node: Node) -> BaseNode:
        """Look up the node class in the registry and instantiate it.

        Phase 1 only executes action nodes; triggers and pollers are handled
        by the trigger manager in Phase 3. We narrow with ``issubclass`` here
        so mypy can see the BaseNode return type.
        """
        try:
            node_cls = self._registry.get(node.type, node.type_version)
        except KeyError as exc:
            msg = f"no registered node for ({node.type!r}, v{node.type_version})"
            raise NodeTypeNotFoundError(msg) from exc
        if not issubclass(node_cls, BaseNode):
            msg = (
                f"node {node.type!r} is registered as a trigger/poller; "
                "only action nodes can be executed by WorkflowExecutor"
            )
            raise NodeTypeNotFoundError(msg)
        return node_cls()

    async def _handle_node_exception(
        self,
        node: Node,
        ctx: ExecutionContext,
        exc: BaseException,
        state: RunState,
        started_at: datetime,
    ) -> NodeRunData:
        """Turn a raised exception into either a run-data entry or a halt."""
        if node.continue_on_fail:
            error_item = Item(
                json={},
                error=NodeError(message=str(exc), code=type(exc).__name__),
            )
            return _elapsed(started_at, [[error_item]], STATUS_ERROR)

        wrapped = NodeExecutionError(str(exc), node_id=node.id, original=exc)
        await self._hooks.on_node_error(ctx, node, wrapped)
        state.mark_failed(node.id, wrapped)
        return NodeRunData(
            items=[],
            execution_time_ms=_elapsed_ms(started_at),
            started_at=started_at,
            status=STATUS_ERROR,
            error=NodeError(message=str(exc), code=type(exc).__name__),
        )


def _seed_inputs_for_roots(
    graph: WorkflowGraph,
    seed_items: list[Item],
) -> dict[str, dict[str, list[Item]]]:
    inputs: dict[str, dict[str, list[Item]]] = defaultdict(lambda: defaultdict(list))
    for root_id in graph.root_ids:
        inputs[root_id][MAIN_PORT] = list(seed_items)
    return inputs


def _compute_initial_pending(graph: WorkflowGraph) -> dict[str, set[str]]:
    return {
        node_id: {edge.source_node_id for edge in graph.incoming(node_id)}
        for node_id in graph.topological_order()
    }


def _propagate_outputs(
    *,
    graph: WorkflowGraph,
    source_id: str,
    outputs: list[list[Item]],
    inputs_by_node: dict[str, dict[str, list[Item]]],
) -> None:
    for edge in graph.outgoing(source_id):
        port_items = _items_for_source_index(outputs, edge.source_index)
        target_bucket = inputs_by_node.setdefault(edge.target_node_id, {})
        target_bucket.setdefault(edge.target_port, []).extend(port_items)


def _advance_readiness(
    *,
    graph: WorkflowGraph,
    just_finished: str,
    pending: dict[str, set[str]],
    ready_queue: deque[str],
) -> None:
    for edge in graph.outgoing(just_finished):
        remaining = pending.get(edge.target_node_id)
        if not remaining:
            continue
        remaining.discard(just_finished)
        if not remaining:
            ready_queue.append(edge.target_node_id)


def _items_for_source_index(outputs: list[list[Item]], source_index: int) -> list[Item]:
    if 0 <= source_index < len(outputs):
        return outputs[source_index]
    return []


def _disabled_run_data(ctx: ExecutionContext, started_at: datetime) -> NodeRunData:
    # Pass-through: a disabled node forwards its ``main`` inputs unchanged so
    # downstream nodes still see data. Matches common automation intuition:
    # toggling a node off is equivalent to replacing it with NoOp.
    pass_through = [list(ctx.get_input(MAIN_PORT))]
    return NodeRunData(
        items=pass_through,
        execution_time_ms=_elapsed_ms(started_at),
        started_at=started_at,
        status=STATUS_DISABLED,
    )


def _elapsed(started_at: datetime, items: list[list[Item]], status: str) -> NodeRunData:
    assert status in {STATUS_SUCCESS, STATUS_ERROR, STATUS_DISABLED}
    return NodeRunData(
        items=items,
        execution_time_ms=_elapsed_ms(started_at),
        started_at=started_at,
        status=status,  # type: ignore[arg-type]
    )


def _elapsed_ms(started_at: datetime) -> int:
    return int((datetime.now(UTC) - started_at).total_seconds() * 1000)


def _exit_context(
    workflow: Workflow,
    state: RunState,
    hooks: LifecycleHooks,
) -> ExecutionContext:
    anchor = workflow.nodes[0] if workflow.nodes else _synthetic_node()
    return ExecutionContext(
        workflow=workflow,
        execution_id=state.execution_id,
        mode=state.mode,
        node=anchor,
        hooks=hooks,
    )


def _synthetic_node() -> Node:
    # Only used when a workflow has zero nodes — degenerate but legal.
    return Node(id="node_synthetic", name="", type="weftlyflow.noop")
