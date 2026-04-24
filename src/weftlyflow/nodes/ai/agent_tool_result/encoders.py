"""Encode tool-execution results back into provider-specific messages.

The ``agent_tool_dispatch`` node normalises outbound tool calls into a
single shape; this module performs the reverse transformation, wrapping
each tool's return value in the message structure the LLM API expects
so the caller can append it to the conversation history for the next
turn.

OpenAI expects one message per tool call::

    {"role": "tool", "tool_call_id": "...", "content": "<str>"}

Anthropic expects a single user message whose ``content`` is a list of
``tool_result`` blocks (the API tolerates one block per message too,
but batching keeps the turn count down)::

    {"role": "user",
     "content": [{"type": "tool_result",
                  "tool_use_id": "...",
                  "content": "<str>",
                  "is_error": <bool>}]}

The ``is_error`` flag is Anthropic-only; OpenAI surfaces errors inside
``content`` as free-form text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

SHAPE_OPENAI: Final[str] = "openai"
SHAPE_ANTHROPIC: Final[str] = "anthropic"
SUPPORTED_SHAPES: Final[frozenset[str]] = frozenset(
    {SHAPE_OPENAI, SHAPE_ANTHROPIC},
)


@dataclass(frozen=True)
class ToolResult:
    """Normalised tool-result record consumed by the encoders."""

    tool_call_id: str
    content: str
    is_error: bool


def encode_openai(results: list[ToolResult]) -> list[dict[str, Any]]:
    """Return one ``role=tool`` message per result."""
    return [
        {
            "role": "tool",
            "tool_call_id": r.tool_call_id,
            "content": r.content,
        }
        for r in results
    ]


def encode_anthropic(
    results: list[ToolResult], *, batch: bool,
) -> list[dict[str, Any]]:
    """Return Anthropic ``tool_result`` messages.

    Args:
        results: One or more normalised tool results.
        batch: When True, all results become a single ``role=user``
            message carrying a list of ``tool_result`` blocks. When
            False, each result produces its own message (useful when a
            caller wants to stream results back one at a time).
    """
    if batch:
        if not results:
            return []
        return [{"role": "user", "content": [_anthropic_block(r) for r in results]}]
    return [
        {"role": "user", "content": [_anthropic_block(r)]}
        for r in results
    ]


def _anthropic_block(r: ToolResult) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": r.tool_call_id,
        "content": r.content,
    }
    if r.is_error:
        block["is_error"] = True
    return block


def coerce_content(raw: Any) -> str:
    """Coerce an arbitrary tool-result payload into a string.

    Strings pass through unchanged. ``None`` becomes ``""``. Everything
    else is JSON-encoded when possible, otherwise stringified — LLM
    APIs require ``content`` to be a string, but tools often return
    rich dicts/lists and users should not need a Set node just to
    flatten them.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, bool | int | float):
        return json.dumps(raw)
    try:
        return json.dumps(raw, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(raw)
