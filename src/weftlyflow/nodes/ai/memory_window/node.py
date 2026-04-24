"""Memory Window node — sliding-window chat history bounded by ``window_size``.

Same shape as :class:`~weftlyflow.nodes.ai.memory_buffer.node.MemoryBufferNode`
but enforces a hard cap of ``window_size`` messages per session. On
``append``, the tail is trimmed so memory growth is bounded — suitable
for long-running chat workflows where the LLM context budget is the
binding constraint.

Buffer and window share the backing store keyed by ``session_id``: a
workflow that uses a buffer node to write and a window node to read
(for example, "keep a permanent log, feed the model only recent turns")
is a supported pattern. Conversely, writing through the window node
trims the backing store for every subsequent reader — that's an
intentional property, not a bug.

Operations mirror the buffer node: ``load`` / ``append`` / ``clear``.
Output item shape is identical.
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

_DEFAULT_WINDOW_SIZE: int = 10
_SUPPORTED_OPERATIONS: frozenset[str] = frozenset({OP_LOAD, OP_APPEND, OP_CLEAR})


class MemoryWindowNode(BaseNode):
    """Session-keyed chat-history buffer capped at ``window_size`` messages."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.memory_window",
        version=1,
        display_name="Memory Window",
        description="Sliding-window chat history with bounded growth per session.",
        icon="icons/memory-window.svg",
        category=NodeCategory.AI,
        group=["ai", "memory"],
        properties=[
            PropertySchema(
                name="session_id",
                display_name="Session ID",
                type="string",
                required=True,
                description="Unique key per conversation.",
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
                name="window_size",
                display_name="Window Size",
                type="number",
                default=_DEFAULT_WINDOW_SIZE,
                required=True,
                description="Maximum messages retained per session.",
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
        """Dispatch one windowed memory operation per input item."""
        seed = items or [Item()]
        results: list[Item] = [_run_one(ctx, item) for item in seed]
        return [results]


def _run_one(ctx: ExecutionContext, item: Item) -> Item:
    params = ctx.resolved_params(item=item)
    session_id = str(params.get("session_id") or "").strip()
    if not session_id:
        msg = "Memory Window: 'session_id' is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    operation = str(params.get("operation") or OP_APPEND).strip()
    if operation not in _SUPPORTED_OPERATIONS:
        msg = f"Memory Window: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    window_size = _coerce_window_size(params.get("window_size"), node_id=ctx.node.id)

    if operation == OP_LOAD:
        messages = load_history(ctx.static_data, session_id)
        if len(messages) > window_size:
            messages = messages[-window_size:]
    elif operation == OP_CLEAR:
        clear_history(ctx.static_data, session_id)
        messages = []
    else:  # append
        new_messages = _coerce_messages(params.get("new_messages"), node_id=ctx.node.id)
        messages = append_history(
            ctx.static_data, session_id, new_messages, max_len=window_size,
        )

    return Item(
        json={
            "session_id": session_id,
            "operation": operation,
            "messages": messages,
            "count": len(messages),
        },
    )


def _coerce_window_size(raw: Any, *, node_id: str) -> int:
    if raw is None or raw == "":
        return _DEFAULT_WINDOW_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Memory Window: 'window_size' must be a positive integer"
        raise NodeExecutionError(msg, node_id=node_id, original=exc) from exc
    if value < 1:
        msg = "Memory Window: 'window_size' must be >= 1"
        raise NodeExecutionError(msg, node_id=node_id)
    return value


def _coerce_messages(raw: Any, *, node_id: str) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list):
        msg = "Memory Window: 'new_messages' must be a JSON array"
        raise NodeExecutionError(msg, node_id=node_id)
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = "Memory Window: each entry in 'new_messages' must be a JSON object"
            raise NodeExecutionError(msg, node_id=node_id)
        out.append(entry)
    return out
