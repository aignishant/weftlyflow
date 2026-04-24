"""Memory Summary node — rolling-summary chat history per session.

Complements :class:`~weftlyflow.nodes.ai.memory_buffer.node.MemoryBufferNode`
(unbounded) and :class:`~weftlyflow.nodes.ai.memory_window.node.MemoryWindowNode`
(hard-trimmed) by keeping *both* a free-form summary string and a
bounded tail of recent messages for each ``session_id``.

The intended pattern is:

1. ``append`` a new user turn. When the retained tail would exceed
   ``max_messages``, the overflow is returned on the ``pending_summary``
   output field in chronological order.
2. The workflow hands ``pending_summary`` (together with the current
   ``summary``) to an LLM node to generate an updated summary.
3. The workflow calls ``set_summary`` with the LLM's output, replacing
   the stored summary. The next ``append`` then operates against the
   new summary.

The node does **not** call any LLM itself — the caller chooses the
provider. This keeps the memory layer orthogonal to LLM nodes (§18.1
of ``IMPLEMENTATION_BIBLE.md``) and avoids hard dependencies from
``weftlyflow.nodes.ai.memory_*`` on ``weftlyflow.nodes.integrations``.

Output item shape::

    {
        "session_id": str,
        "operation": str,
        "summary": str,
        "messages": list[dict],
        "count": int,
        "pending_summary": list[dict],
    }

``pending_summary`` is only non-empty on ``append`` when the window
overflowed; for every other operation it is ``[]``.
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
    append_summary_messages,
    clear_summary,
    load_summary,
    replace_summary,
)
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

OP_LOAD: str = "load"
OP_APPEND: str = "append"
OP_SET_SUMMARY: str = "set_summary"
OP_CLEAR: str = "clear"

_DEFAULT_MAX_MESSAGES: int = 10
_SUPPORTED_OPERATIONS: frozenset[str] = frozenset(
    {OP_LOAD, OP_APPEND, OP_SET_SUMMARY, OP_CLEAR},
)


class MemorySummaryNode(BaseNode):
    """Session-keyed chat history with a bounded tail and a rolling summary."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.memory_summary",
        version=1,
        display_name="Memory Summary",
        description=(
            "Rolling-summary chat history: keeps a bounded tail of recent "
            "messages plus a caller-managed summary string."
        ),
        icon="icons/memory-summary.svg",
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
                    PropertyOption(value=OP_SET_SUMMARY, label="Set Summary"),
                    PropertyOption(value=OP_CLEAR, label="Clear"),
                ],
            ),
            PropertySchema(
                name="max_messages",
                display_name="Max Messages",
                type="number",
                default=_DEFAULT_MAX_MESSAGES,
                required=True,
                description=(
                    "Maximum messages retained per session. Overflow is "
                    "returned on 'pending_summary'."
                ),
            ),
            PropertySchema(
                name="new_messages",
                display_name="New Messages",
                type="json",
                description='[{"role": "user", "content": "..."}]',
                display_options=DisplayOptions(show={"operation": [OP_APPEND]}),
            ),
            PropertySchema(
                name="summary_text",
                display_name="Summary Text",
                type="string",
                description="Replaces the stored rolling summary.",
                display_options=DisplayOptions(show={"operation": [OP_SET_SUMMARY]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Dispatch one summary-memory operation per input item."""
        seed = items or [Item()]
        results: list[Item] = [_run_one(ctx, item) for item in seed]
        return [results]


def _run_one(ctx: ExecutionContext, item: Item) -> Item:
    params = ctx.resolved_params(item=item)
    session_id = str(params.get("session_id") or "").strip()
    if not session_id:
        msg = "Memory Summary: 'session_id' is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    operation = str(params.get("operation") or OP_APPEND).strip()
    if operation not in _SUPPORTED_OPERATIONS:
        msg = f"Memory Summary: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)

    pending: list[dict[str, Any]] = []
    if operation == OP_LOAD:
        summary, messages = load_summary(ctx.static_data, session_id)
    elif operation == OP_CLEAR:
        clear_summary(ctx.static_data, session_id)
        summary, messages = "", []
    elif operation == OP_SET_SUMMARY:
        summary_text = _coerce_summary_text(params.get("summary_text"))
        summary, messages = replace_summary(ctx.static_data, session_id, summary_text)
    else:  # append
        max_messages = _coerce_max_messages(
            params.get("max_messages"), node_id=ctx.node.id,
        )
        new_messages = _coerce_messages(params.get("new_messages"), node_id=ctx.node.id)
        summary, messages, pending = append_summary_messages(
            ctx.static_data,
            session_id,
            new_messages,
            max_messages=max_messages,
        )

    return Item(
        json={
            "session_id": session_id,
            "operation": operation,
            "summary": summary,
            "messages": messages,
            "count": len(messages),
            "pending_summary": pending,
        },
    )


def _coerce_max_messages(raw: Any, *, node_id: str) -> int:
    if raw is None or raw == "":
        return _DEFAULT_MAX_MESSAGES
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Memory Summary: 'max_messages' must be a positive integer"
        raise NodeExecutionError(msg, node_id=node_id, original=exc) from exc
    if value < 1:
        msg = "Memory Summary: 'max_messages' must be >= 1"
        raise NodeExecutionError(msg, node_id=node_id)
    return value


def _coerce_summary_text(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw)


def _coerce_messages(raw: Any, *, node_id: str) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list):
        msg = "Memory Summary: 'new_messages' must be a JSON array"
        raise NodeExecutionError(msg, node_id=node_id)
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = "Memory Summary: each entry in 'new_messages' must be a JSON object"
            raise NodeExecutionError(msg, node_id=node_id)
        out.append(entry)
    return out
