"""Memory Buffer node — append-only chat history keyed by ``session_id``.

Stores the full conversation for a session in workflow static data so
subsequent runs against the same ``session_id`` (a chat-trigger fire,
an agent's tool loop, a retry) see the prior turns. Companion to
:class:`~weftlyflow.nodes.ai.memory_window.node.MemoryWindowNode`,
which enforces a bounded window; the buffer keeps history forever
until explicitly cleared.

Operations:

* ``load`` — return the current history as a single item.
* ``append`` — push ``new_messages`` onto the history and return the
  new full list.
* ``clear`` — drop the session's history.

Output item shape::

    {
        "session_id": str,
        "operation": str,
        "messages": list[dict],
        "count": int,
    }
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    DisplayOptions,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.ai.memory_store import (
    append_history,
    clear_history,
    load_history,
)
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

OP_LOAD: str = "load"
OP_APPEND: str = "append"
OP_CLEAR: str = "clear"

_SUPPORTED_OPERATIONS: frozenset[str] = frozenset({OP_LOAD, OP_APPEND, OP_CLEAR})


class MemoryBufferNode(BaseNode):
    """Session-keyed chat-history buffer with unbounded retention."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.memory_buffer",
        version=1,
        display_name="Memory Buffer",
        description="Persist chat history per session across workflow runs.",
        icon="icons/memory-buffer.svg",
        category=NodeCategory.AI,
        group=["ai", "memory"],
        properties=[
            PropertySchema(
                name="session_id",
                display_name="Session ID",
                type="string",
                required=True,
                description="Unique key per conversation (often '{{ $json.session_id }}').",
            ),
            PropertySchema(
                name="operation",
                display_name="Operation",
                type="options",
                default=OP_APPEND,
                required=True,
                options=[
                    PropertyOption(value=OP_LOAD, label="Load"),
                    PropertyOption(value=OP_APPEND, label="Append"),
                    PropertyOption(value=OP_CLEAR, label="Clear"),
                ],
            ),
            PropertySchema(
                name="new_messages",
                display_name="New Messages",
                type="json",
                description='[{"role": "user", "content": "..."}]',
                display_options=DisplayOptions(show={"operation": [OP_APPEND]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Dispatch one memory operation per input item."""
        seed = items or [Item()]
        results: list[Item] = [_run_one(ctx, item) for item in seed]
        return [results]


def _run_one(ctx: ExecutionContext, item: Item) -> Item:
    params = ctx.resolved_params(item=item)
    session_id = str(params.get("session_id") or "").strip()
    if not session_id:
        msg = "Memory Buffer: 'session_id' is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    operation = str(params.get("operation") or OP_APPEND).strip()
    if operation not in _SUPPORTED_OPERATIONS:
        msg = f"Memory Buffer: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)

    if operation == OP_LOAD:
        messages = load_history(ctx.static_data, session_id)
    elif operation == OP_CLEAR:
        clear_history(ctx.static_data, session_id)
        messages = []
    else:  # append
        new_messages = _coerce_messages(params.get("new_messages"), node_id=ctx.node.id)
        messages = append_history(ctx.static_data, session_id, new_messages)

    return Item(
        json={
            "session_id": session_id,
            "operation": operation,
            "messages": messages,
            "count": len(messages),
        },
    )


def _coerce_messages(raw: Any, *, node_id: str) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list):
        msg = "Memory Buffer: 'new_messages' must be a JSON array"
        raise NodeExecutionError(msg, node_id=node_id)
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = "Memory Buffer: each entry in 'new_messages' must be a JSON object"
            raise NodeExecutionError(msg, node_id=node_id)
        out.append(entry)
    return out
