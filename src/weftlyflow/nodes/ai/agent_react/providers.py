"""Per-provider request builders and response extractors for ``agent_react``.

Weftlyflow exposes a single neutral tool-definition shape at the node
boundary::

    {"name": "...", "description": "...", "parameters": {...JSON schema...}}

and this module adapts that shape to each provider's native wire
format:

* **OpenAI** Chat Completions (``POST /v1/chat/completions``) wraps
  every tool in ``{"type": "function", "function": {...}}`` and puts
  tool calls under ``choices[0].message.tool_calls``.
* **Anthropic** Messages (``POST /v1/messages``) takes tools as a flat
  list with ``input_schema`` in place of ``parameters``, expects
  ``system`` as a top-level field (not a message), and returns tool
  uses as interleaved ``content`` blocks.

The returned ``ProviderRequest`` carries everything the node needs to
issue the call; the ``Turn`` record captures everything needed to emit
output items and append the assistant message to the caller's history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from weftlyflow.nodes.ai.agent_tool_dispatch.parsers import (
    SHAPE_ANTHROPIC,
    SHAPE_OPENAI,
    ToolCall,
    parse,
)

PROVIDER_OPENAI: Final[str] = "openai"
PROVIDER_ANTHROPIC: Final[str] = "anthropic"
SUPPORTED_PROVIDERS: Final[frozenset[str]] = frozenset(
    {PROVIDER_OPENAI, PROVIDER_ANTHROPIC},
)

OPENAI_BASE_URL: Final[str] = "https://api.openai.com"
OPENAI_CHAT_PATH: Final[str] = "/v1/chat/completions"
ANTHROPIC_BASE_URL: Final[str] = "https://api.anthropic.com"
ANTHROPIC_MESSAGES_PATH: Final[str] = "/v1/messages"

_ANTHROPIC_DEFAULT_MAX_TOKENS: Final[int] = 1024

_SLUG_TO_PROVIDER: Final[dict[str, str]] = {
    "weftlyflow.openai_api": PROVIDER_OPENAI,
    "weftlyflow.anthropic_api": PROVIDER_ANTHROPIC,
}


@dataclass(frozen=True)
class ProviderRequest:
    """What the node needs to issue one LLM call."""

    base_url: str
    path: str
    body: dict[str, Any]


@dataclass(frozen=True)
class Turn:
    """Parsed outcome of one LLM turn.

    ``assistant_message`` is the provider-native assistant message the
    caller should append to its history so the conversation stays
    coherent across turns. ``tool_calls`` is empty when the turn
    produced a final answer.
    """

    tool_calls: list[ToolCall]
    content: str
    assistant_message: dict[str, Any]


def provider_for_slug(slug: str) -> str | None:
    """Return the provider name for a credential slug, or ``None``."""
    return _SLUG_TO_PROVIDER.get(slug)


def build_request(
    provider: str,
    *,
    history: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    system: str,
    temperature: float | None,
    max_tokens: int | None,
) -> ProviderRequest:
    """Dispatch to the provider-specific builder or raise :class:`ValueError`."""
    if provider == PROVIDER_OPENAI:
        return _build_openai(
            history=history,
            tools=tools,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider == PROVIDER_ANTHROPIC:
        return _build_anthropic(
            history=history,
            tools=tools,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    msg = f"unsupported provider {provider!r}"
    raise ValueError(msg)


def parse_turn(provider: str, response: dict[str, Any]) -> Turn:
    """Normalise a provider response into a :class:`Turn`."""
    if provider == PROVIDER_OPENAI:
        return _parse_openai(response)
    if provider == PROVIDER_ANTHROPIC:
        return _parse_anthropic(response)
    msg = f"unsupported provider {provider!r}"
    raise ValueError(msg)


# --- OpenAI ---------------------------------------------------------


def _build_openai(
    *,
    history: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    system: str,
    temperature: float | None,
    max_tokens: int | None,
) -> ProviderRequest:
    messages = _ensure_openai_system(history, system)
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        body["tools"] = [_openai_tool(t) for t in tools]
    if temperature is not None:
        body["temperature"] = temperature
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    return ProviderRequest(
        base_url=OPENAI_BASE_URL, path=OPENAI_CHAT_PATH, body=body,
    )


def _ensure_openai_system(
    history: list[dict[str, Any]], system: str,
) -> list[dict[str, Any]]:
    if not system:
        return list(history)
    if history and history[0].get("role") == "system":
        return list(history)
    return [{"role": "system", "content": system}, *history]


def _openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    name = str(tool.get("name") or "").strip()
    if not name:
        msg = "tool definition is missing 'name'"
        raise ValueError(msg)
    function: dict[str, Any] = {"name": name}
    description = tool.get("description")
    if isinstance(description, str) and description:
        function["description"] = description
    parameters = tool.get("parameters")
    if isinstance(parameters, dict):
        function["parameters"] = parameters
    else:
        # OpenAI requires a schema; use the empty-object default.
        function["parameters"] = {"type": "object", "properties": {}}
    return {"type": "function", "function": function}


def _parse_openai(response: dict[str, Any]) -> Turn:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return Turn(tool_calls=[], content="", assistant_message={})
    first = choices[0]
    if not isinstance(first, dict):
        return Turn(tool_calls=[], content="", assistant_message={})
    message = first.get("message")
    if not isinstance(message, dict):
        return Turn(tool_calls=[], content="", assistant_message={})
    raw_content = message.get("content")
    content = raw_content if isinstance(raw_content, str) else ""
    tool_calls = parse(SHAPE_OPENAI, message.get("tool_calls"))
    return Turn(
        tool_calls=tool_calls,
        content=content,
        assistant_message=dict(message),
    )


# --- Anthropic ------------------------------------------------------


def _build_anthropic(
    *,
    history: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    system: str,
    temperature: float | None,
    max_tokens: int | None,
) -> ProviderRequest:
    messages = _strip_anthropic_system(history)
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": (
            max_tokens if max_tokens is not None else _ANTHROPIC_DEFAULT_MAX_TOKENS
        ),
    }
    effective_system = system or _extract_inline_system(history)
    if effective_system:
        body["system"] = effective_system
    if tools:
        body["tools"] = [_anthropic_tool(t) for t in tools]
    if temperature is not None:
        body["temperature"] = temperature
    return ProviderRequest(
        base_url=ANTHROPIC_BASE_URL, path=ANTHROPIC_MESSAGES_PATH, body=body,
    )


def _strip_anthropic_system(
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Anthropic does not accept role=system in messages; it goes in a
    # dedicated top-level field. Users carrying an OpenAI-shaped history
    # can still wire it through without rebuilding it by hand.
    return [m for m in history if m.get("role") != "system"]


def _extract_inline_system(history: list[dict[str, Any]]) -> str:
    for message in history:
        if message.get("role") == "system":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                return "".join(parts)
    return ""


def _anthropic_tool(tool: dict[str, Any]) -> dict[str, Any]:
    name = str(tool.get("name") or "").strip()
    if not name:
        msg = "tool definition is missing 'name'"
        raise ValueError(msg)
    out: dict[str, Any] = {"name": name}
    description = tool.get("description")
    if isinstance(description, str) and description:
        out["description"] = description
    # Anthropic uses 'input_schema'; accept the neutral 'parameters' key
    # and rename, or pass through if the user supplied 'input_schema'.
    schema = tool.get("input_schema")
    if not isinstance(schema, dict):
        schema = tool.get("parameters")
    out["input_schema"] = schema if isinstance(schema, dict) else {
        "type": "object", "properties": {},
    }
    return out


def _parse_anthropic(response: dict[str, Any]) -> Turn:
    blocks = response.get("content")
    if not isinstance(blocks, list):
        return Turn(tool_calls=[], content="", assistant_message={})
    text_parts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    tool_calls = parse(SHAPE_ANTHROPIC, blocks)
    assistant_message = {
        "role": response.get("role", "assistant"),
        "content": list(blocks),
    }
    return Turn(
        tool_calls=tool_calls,
        content="".join(text_parts),
        assistant_message=assistant_message,
    )
