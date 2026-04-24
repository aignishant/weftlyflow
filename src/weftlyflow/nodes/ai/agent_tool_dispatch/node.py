"""Agent Tool Dispatch node - fan LLM tool calls out to a dedicated port.

Takes an LLM response item (OpenAI or Anthropic shape) and emits:

* one item per tool call on the ``calls`` port, carrying
  ``{tool_name, tool_args, tool_call_id, call_index, call_total}``;
* zero or one item on the ``content`` port, carrying the plain-text
  response when present.

This is pure data transformation - the node never calls an LLM. It is
the bridge between an LLM integration node and whatever executes the
tool (a Switch, an HTTP Request, a sub-workflow call). Building ReAct
or function-calling agents then reduces to wiring this dispatcher
between the LLM and the tool executors, with the memory nodes closing
the loop.

Parameters:

* ``shape`` - ``openai`` (default), ``anthropic``, or ``custom``.
* ``tool_calls_path`` - dotted path to the tool-calls list. Defaults
  pair with each shape's canonical response structure.
* ``content_path`` - dotted path to the plain-text response.
* ``on_empty`` - ``skip`` (default) drops the item when no tool calls
  and no content; ``emit_content`` forwards empty-content items;
  ``error`` raises.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.domain.workflow import Port
from weftlyflow.nodes.ai.agent_tool_dispatch.parsers import (
    SHAPE_ANTHROPIC,
    SHAPE_CUSTOM,
    SHAPE_OPENAI,
    SUPPORTED_SHAPES,
    parse,
)
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.utils import get_path

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_OPENAI_DEFAULT_CALLS_PATH: str = "response.choices.0.message.tool_calls"
_OPENAI_DEFAULT_CONTENT_PATH: str = "response.choices.0.message.content"
_ANTHROPIC_DEFAULT_CALLS_PATH: str = "response.content"
_ANTHROPIC_DEFAULT_CONTENT_PATH: str = ""

ON_EMPTY_SKIP: str = "skip"
ON_EMPTY_EMIT_CONTENT: str = "emit_content"
ON_EMPTY_ERROR: str = "error"
_SUPPORTED_ON_EMPTY: frozenset[str] = frozenset(
    {ON_EMPTY_SKIP, ON_EMPTY_EMIT_CONTENT, ON_EMPTY_ERROR},
)


class AgentToolDispatchNode(BaseNode):
    """Split an LLM response into tool-call and content output streams."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.agent_tool_dispatch",
        version=1,
        display_name="Agent: Tool Dispatch",
        description=(
            "Fan LLM tool calls to a 'calls' port and plain-text "
            "content to a 'content' port."
        ),
        icon="icons/agent-tool-dispatch.svg",
        category=NodeCategory.AI,
        group=["ai", "agent"],
        inputs=[Port(name="main")],
        outputs=[Port(name="calls"), Port(name="content")],
        properties=[
            PropertySchema(
                name="shape",
                display_name="Provider Shape",
                type="options",
                default=SHAPE_OPENAI,
                options=[
                    PropertyOption(value=SHAPE_OPENAI, label="OpenAI"),
                    PropertyOption(value=SHAPE_ANTHROPIC, label="Anthropic"),
                    PropertyOption(value=SHAPE_CUSTOM, label="Custom / pre-normalised"),
                ],
            ),
            PropertySchema(
                name="tool_calls_path",
                display_name="Tool Calls Path",
                type="string",
                description=(
                    "Dotted path to the tool-calls list. Leave empty "
                    "to use the default for the selected shape."
                ),
            ),
            PropertySchema(
                name="content_path",
                display_name="Content Path",
                type="string",
                description=(
                    "Dotted path to the plain-text response. Leave "
                    "empty to use the shape default. For Anthropic, "
                    "content is assembled from 'text' blocks in the "
                    "same list as tool calls."
                ),
            ),
            PropertySchema(
                name="on_empty",
                display_name="On Empty",
                type="options",
                default=ON_EMPTY_SKIP,
                options=[
                    PropertyOption(value=ON_EMPTY_SKIP, label="Skip"),
                    PropertyOption(
                        value=ON_EMPTY_EMIT_CONTENT,
                        label="Emit content item even if empty",
                    ),
                    PropertyOption(value=ON_EMPTY_ERROR, label="Raise"),
                ],
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Fan tool calls to port 0, content to port 1."""
        calls_out: list[Item] = []
        content_out: list[Item] = []
        for item in items:
            calls, content = _dispatch_one(ctx, item)
            calls_out.extend(calls)
            content_out.extend(content)
        return [calls_out, content_out]


def _dispatch_one(
    ctx: ExecutionContext, item: Item,
) -> tuple[list[Item], list[Item]]:
    params = ctx.resolved_params(item=item)
    shape = str(params.get("shape") or SHAPE_OPENAI)
    if shape not in SUPPORTED_SHAPES:
        msg = f"Agent Tool Dispatch: unsupported shape {shape!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    on_empty = str(params.get("on_empty") or ON_EMPTY_SKIP)
    if on_empty not in _SUPPORTED_ON_EMPTY:
        msg = f"Agent Tool Dispatch: unsupported on_empty {on_empty!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)

    source = item.json if isinstance(item.json, dict) else {}
    calls_path = _resolve_calls_path(params, shape)
    content_path = _resolve_content_path(params, shape)

    raw_calls = get_path(source, calls_path, default=None) if calls_path else None
    if shape == SHAPE_ANTHROPIC:
        calls, content_text = _extract_anthropic(raw_calls)
    else:
        calls = parse(shape, raw_calls)
        content_text = _extract_text(source, content_path)

    call_items = _call_items(calls, item)
    content_items = _content_items(content_text, item)

    if not call_items and not content_items:
        if on_empty == ON_EMPTY_ERROR:
            msg = "Agent Tool Dispatch: no tool calls and no content in input"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        if on_empty == ON_EMPTY_EMIT_CONTENT:
            content_items = [_wrap_content("", item)]
    return call_items, content_items


def _resolve_calls_path(params: dict[str, Any], shape: str) -> str:
    override = params.get("tool_calls_path")
    if isinstance(override, str) and override:
        return override
    if shape == SHAPE_ANTHROPIC:
        return _ANTHROPIC_DEFAULT_CALLS_PATH
    return _OPENAI_DEFAULT_CALLS_PATH


def _resolve_content_path(params: dict[str, Any], shape: str) -> str:
    override = params.get("content_path")
    if isinstance(override, str) and override:
        return override
    if shape == SHAPE_ANTHROPIC:
        return _ANTHROPIC_DEFAULT_CONTENT_PATH
    return _OPENAI_DEFAULT_CONTENT_PATH


def _extract_anthropic(raw: Any) -> tuple[list[Any], str]:
    """Anthropic interleaves tool_use and text blocks in one list."""
    if not isinstance(raw, list):
        return [], ""
    tool_blocks: list[Any] = []
    text_parts: list[str] = []
    for block in raw:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            tool_blocks.append(block)
        elif block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    return parse(SHAPE_ANTHROPIC, tool_blocks), "".join(text_parts)


def _extract_text(source: dict[str, Any], path: str) -> str:
    if not path:
        return ""
    raw = get_path(source, path, default="")
    if raw is None:
        return ""
    return raw if isinstance(raw, str) else str(raw)


def _call_items(calls: list[Any], source: Item) -> list[Item]:
    total = len(calls)
    return [
        Item(
            json={
                "tool_name": call.tool_name,
                "tool_args": call.tool_args,
                "tool_call_id": call.tool_call_id,
                "call_index": idx,
                "call_total": total,
            },
            binary=source.binary,
            paired_item=source.paired_item,
            error=source.error,
        )
        for idx, call in enumerate(calls)
    ]


def _content_items(content: str, source: Item) -> list[Item]:
    if not content:
        return []
    return [_wrap_content(content, source)]


def _wrap_content(content: str, source: Item) -> Item:
    return Item(
        json={"content": content},
        binary=source.binary,
        paired_item=source.paired_item,
        error=source.error,
    )
