"""Normalise LLM tool-call shapes to a single canonical record.

OpenAI chat-completion responses nest tool calls at
``response.choices[0].message.tool_calls`` with the shape::

    {"id": "call_x", "type": "function",
     "function": {"name": "...", "arguments": "<JSON-encoded string>"}}

Anthropic message responses flatten them into ``response.content`` as
a list of content blocks, where tool uses have ``type == "tool_use"``::

    {"type": "tool_use", "id": "toolu_x",
     "name": "...", "input": {...}}

This module converts either into ``ToolCall(tool_name, tool_args,
tool_call_id)`` so the dispatch node can emit uniform output items
regardless of provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

SHAPE_OPENAI: Final[str] = "openai"
SHAPE_ANTHROPIC: Final[str] = "anthropic"
SHAPE_CUSTOM: Final[str] = "custom"
SUPPORTED_SHAPES: Final[frozenset[str]] = frozenset(
    {SHAPE_OPENAI, SHAPE_ANTHROPIC, SHAPE_CUSTOM},
)


@dataclass(frozen=True)
class ToolCall:
    """Normalised tool-call record used by the dispatch node."""

    tool_name: str
    tool_args: dict[str, Any]
    tool_call_id: str


def parse(shape: str, raw: Any) -> list[ToolCall]:
    """Normalise ``raw`` tool-call list according to ``shape``.

    Args:
        shape: One of :data:`SHAPE_OPENAI`, :data:`SHAPE_ANTHROPIC`,
            :data:`SHAPE_CUSTOM`.
        raw: The list found at the configured tool-calls path. Any
            non-list value yields an empty result rather than raising,
            because the absence of tool calls is the common case and
            should not break the workflow.

    Returns:
        Zero or more :class:`ToolCall` records. Entries that cannot
        be parsed are skipped.

    Raises:
        ValueError: if ``shape`` is not supported.
    """
    if shape not in SUPPORTED_SHAPES:
        msg = f"unsupported shape {shape!r}"
        raise ValueError(msg)
    if not isinstance(raw, list):
        return []
    if shape == SHAPE_OPENAI:
        return [call for entry in raw if (call := _parse_openai(entry))]
    if shape == SHAPE_ANTHROPIC:
        return [call for entry in raw if (call := _parse_anthropic(entry))]
    return [call for entry in raw if (call := _parse_custom(entry))]


def _parse_openai(entry: Any) -> ToolCall | None:
    if not isinstance(entry, dict):
        return None
    fn = entry.get("function")
    if not isinstance(fn, dict):
        return None
    name = fn.get("name")
    if not isinstance(name, str) or not name:
        return None
    args = _decode_args(fn.get("arguments"))
    call_id = str(entry.get("id") or "")
    return ToolCall(tool_name=name, tool_args=args, tool_call_id=call_id)


def _parse_anthropic(entry: Any) -> ToolCall | None:
    if not isinstance(entry, dict):
        return None
    if entry.get("type") != "tool_use":
        return None
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        return None
    args = entry.get("input")
    if not isinstance(args, dict):
        args = {}
    return ToolCall(
        tool_name=name,
        tool_args=dict(args),
        tool_call_id=str(entry.get("id") or ""),
    )


def _parse_custom(entry: Any) -> ToolCall | None:
    """Accept a pre-normalised record - users who hand-roll LLM plumbing."""
    if not isinstance(entry, dict):
        return None
    name = entry.get("tool_name") or entry.get("name")
    if not isinstance(name, str) or not name:
        return None
    raw_args = entry.get("tool_args")
    if raw_args is None:
        raw_args = entry.get("arguments") or entry.get("input")
    args = _decode_args(raw_args) if not isinstance(raw_args, dict) else dict(raw_args)
    call_id = str(entry.get("tool_call_id") or entry.get("id") or "")
    return ToolCall(tool_name=name, tool_args=args, tool_call_id=call_id)


def _decode_args(raw: Any) -> dict[str, Any]:
    """OpenAI encodes ``arguments`` as a JSON string; decode it defensively."""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw:
        try:
            decoded = json.loads(raw)
        except ValueError:
            return {"_raw": raw}
        if isinstance(decoded, dict):
            return decoded
        return {"_value": decoded}
    return {}
