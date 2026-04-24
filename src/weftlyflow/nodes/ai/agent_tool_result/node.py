"""Agent Tool Result node - close the ReAct loop.

Takes each tool-execution result flowing back from the tool executor
(an HTTP Request, Switch-dispatched sub-workflow, etc.) and shapes it
into a provider-specific message the LLM can consume on its next turn.

Pairs with :class:`weftlyflow.nodes.ai.agent_tool_dispatch.AgentToolDispatchNode`:

* ``agent_tool_dispatch`` splits the LLM's outbound tool calls into a
  dedicated ``calls`` port;
* the workflow author wires those calls to the executor(s);
* ``agent_tool_result`` encodes the executor output into a message
  ready to append to the LLM's history.

Parameters:

* ``shape`` - ``openai`` (default) or ``anthropic``.
* ``tool_call_id_field`` - JSON key carrying the id from dispatch.
* ``result_field`` - JSON key carrying the tool's return value.
* ``is_error_field`` - JSON key for a boolean error marker
  (Anthropic only; OpenAI surfaces errors in ``content``).
* ``batch_anthropic`` - when True, all input items become a single
  Anthropic message containing a list of ``tool_result`` blocks. When
  False, each input becomes its own message.
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
from weftlyflow.nodes.ai.agent_tool_result.encoders import (
    SHAPE_ANTHROPIC,
    SHAPE_OPENAI,
    SUPPORTED_SHAPES,
    ToolResult,
    coerce_content,
    encode_anthropic,
    encode_openai,
)
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_DEFAULT_TOOL_CALL_ID_FIELD: str = "tool_call_id"
_DEFAULT_RESULT_FIELD: str = "result"
_DEFAULT_IS_ERROR_FIELD: str = "is_error"


class AgentToolResultNode(BaseNode):
    """Wrap tool outputs into provider-shaped messages for the next LLM turn."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.agent_tool_result",
        version=1,
        display_name="Agent: Tool Result",
        description=(
            "Encode tool-execution output into an OpenAI or Anthropic "
            "tool-result message ready for the next LLM turn."
        ),
        icon="icons/agent-tool-result.svg",
        category=NodeCategory.AI,
        group=["ai", "agent"],
        properties=[
            PropertySchema(
                name="shape",
                display_name="Provider Shape",
                type="options",
                default=SHAPE_OPENAI,
                options=[
                    PropertyOption(value=SHAPE_OPENAI, label="OpenAI"),
                    PropertyOption(value=SHAPE_ANTHROPIC, label="Anthropic"),
                ],
            ),
            PropertySchema(
                name="tool_call_id_field",
                display_name="Tool Call ID Field",
                type="string",
                default=_DEFAULT_TOOL_CALL_ID_FIELD,
                description=(
                    "JSON key carrying the tool_call_id emitted by "
                    "agent_tool_dispatch."
                ),
            ),
            PropertySchema(
                name="result_field",
                display_name="Result Field",
                type="string",
                default=_DEFAULT_RESULT_FIELD,
                description=(
                    "JSON key holding the executor's return value. "
                    "Non-string values are JSON-encoded."
                ),
            ),
            PropertySchema(
                name="is_error_field",
                display_name="Is-Error Field",
                type="string",
                default=_DEFAULT_IS_ERROR_FIELD,
                description=(
                    "JSON key whose truthy value marks the tool run as "
                    "failed. Anthropic only."
                ),
                display_options=DisplayOptions(show={"shape": [SHAPE_ANTHROPIC]}),
            ),
            PropertySchema(
                name="batch_anthropic",
                display_name="Batch Into Single Message",
                type="boolean",
                default=True,
                description=(
                    "Group every input item into one Anthropic user "
                    "message. When off, each item emits its own message."
                ),
                display_options=DisplayOptions(show={"shape": [SHAPE_ANTHROPIC]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Emit one or more messages shaped for the configured provider."""
        if not items:
            return [[]]
        shape, batch = _resolve_shape(ctx, items[0])
        results = [_to_tool_result(ctx, item, shape) for item in items]
        messages = (
            encode_openai(results)
            if shape == SHAPE_OPENAI
            else encode_anthropic(results, batch=batch)
        )
        return [[Item(json={"message": msg}) for msg in messages]]


def _resolve_shape(ctx: ExecutionContext, first: Item) -> tuple[str, bool]:
    params = ctx.resolved_params(item=first)
    shape = str(params.get("shape") or SHAPE_OPENAI)
    if shape not in SUPPORTED_SHAPES:
        msg = f"Agent Tool Result: unsupported shape {shape!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    batch = bool(params.get("batch_anthropic", True))
    return shape, batch


def _to_tool_result(
    ctx: ExecutionContext, item: Item, shape: str,
) -> ToolResult:
    params = ctx.resolved_params(item=item)
    source = item.json if isinstance(item.json, dict) else {}
    id_field = str(params.get("tool_call_id_field") or _DEFAULT_TOOL_CALL_ID_FIELD)
    result_field = str(params.get("result_field") or _DEFAULT_RESULT_FIELD)
    err_field = str(params.get("is_error_field") or _DEFAULT_IS_ERROR_FIELD)

    tool_call_id = _coerce_id(source.get(id_field))
    if not tool_call_id:
        msg = (
            f"Agent Tool Result: input is missing tool_call_id at "
            f"{id_field!r}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)

    content = coerce_content(source.get(result_field))
    is_error = _coerce_bool(source.get(err_field)) if shape == SHAPE_ANTHROPIC else False
    return ToolResult(
        tool_call_id=tool_call_id,
        content=content,
        is_error=is_error,
    )


def _coerce_id(raw: Any) -> str:
    if raw is None:
        return ""
    return raw if isinstance(raw, str) else str(raw)


def _coerce_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "1", "yes", "y"}
    return bool(raw)
