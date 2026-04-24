"""Per-operation request builders for the Mistral node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://api.mistral.ai``.

Mistral's La Plateforme API is largely OpenAI-compatible:
``/v1/chat/completions`` accepts the same ``messages`` list shape and
``/v1/embeddings`` the same ``input`` + ``model`` pair. The
distinctive Mistral endpoint is ``/v1/fim/completions``
(fill-in-the-middle for code models like ``codestral-latest``),
which takes ``prompt`` + optional ``suffix`` instead of a message
list — there's no OpenAI equivalent.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.mistral.constants import (
    DEFAULT_EMBED_MODEL,
    DEFAULT_FIM_MODEL,
    DEFAULT_MODEL,
    OP_CHAT_COMPLETION,
    OP_CREATE_EMBEDDING,
    OP_FIM_COMPLETION,
    OP_LIST_MODELS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Mistral: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_chat_completion(params: dict[str, Any]) -> RequestSpec:
    model = str(params.get("model") or DEFAULT_MODEL).strip()
    messages = _coerce_messages(params.get("messages"))
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
    _apply_numeric(params, body, "temperature", kind="float")
    _apply_numeric(params, body, "top_p", kind="float")
    _apply_numeric(params, body, "max_tokens", body_key="max_tokens", kind="pos_int")
    response_format = str(params.get("response_format") or "").strip()
    if response_format:
        if response_format not in {"text", "json_object"}:
            msg = "Mistral: 'response_format' must be 'text' or 'json_object'"
            raise ValueError(msg)
        body["response_format"] = {"type": response_format}
    tools = params.get("tools")
    if tools is not None and tools != "":
        if not isinstance(tools, list):
            msg = "Mistral: 'tools' must be a JSON array"
            raise ValueError(msg)
        body["tools"] = tools
    safe_prompt = params.get("safe_prompt")
    if safe_prompt is not None and safe_prompt != "":
        body["safe_prompt"] = bool(safe_prompt)
    return "POST", "/v1/chat/completions", body, {}


def _build_fim_completion(params: dict[str, Any]) -> RequestSpec:
    model = str(params.get("model") or DEFAULT_FIM_MODEL).strip()
    prompt = params.get("prompt")
    if prompt is None or prompt == "":
        msg = "Mistral: 'prompt' is required for FIM completion"
        raise ValueError(msg)
    body: dict[str, Any] = {"model": model, "prompt": str(prompt), "stream": False}
    suffix = params.get("suffix")
    if suffix is not None and suffix != "":
        body["suffix"] = str(suffix)
    _apply_numeric(params, body, "temperature", kind="float")
    _apply_numeric(params, body, "top_p", kind="float")
    _apply_numeric(params, body, "max_tokens", body_key="max_tokens", kind="pos_int")
    return "POST", "/v1/fim/completions", body, {}


def _build_create_embedding(params: dict[str, Any]) -> RequestSpec:
    model = str(params.get("model") or DEFAULT_EMBED_MODEL).strip()
    raw_input = params.get("input")
    if raw_input is None or raw_input == "":
        msg = "Mistral: 'input' is required"
        raise ValueError(msg)
    body: dict[str, Any] = {"model": model, "input": raw_input}
    return "POST", "/v1/embeddings", body, {}


def _build_list_models(params: dict[str, Any]) -> RequestSpec:
    del params
    return "GET", "/v1/models", None, {}


def _coerce_messages(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        msg = "Mistral: 'messages' is required"
        raise ValueError(msg)
    if not isinstance(raw, list) or not raw:
        msg = "Mistral: 'messages' must be a non-empty list"
        raise ValueError(msg)
    normalized: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = "Mistral: each message must be an object with 'role' and 'content'"
            raise ValueError(msg)
        role = str(entry.get("role") or "").strip()
        if not role:
            msg = "Mistral: message is missing 'role'"
            raise ValueError(msg)
        if "content" not in entry:
            msg = "Mistral: message is missing 'content'"
            raise ValueError(msg)
        normalized.append({**entry, "role": role})
    return normalized


def _apply_numeric(
    params: dict[str, Any],
    body: dict[str, Any],
    param_name: str,
    *,
    body_key: str | None = None,
    kind: str,
) -> None:
    value = params.get(param_name)
    if value is None or value == "":
        return
    target = body_key or param_name
    body[target] = (
        _coerce_positive_int(value, field=param_name)
        if kind == "pos_int"
        else _coerce_float(value, field=param_name)
    )


def _coerce_float(raw: Any, *, field: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Mistral: {field!r} must be numeric"
        raise ValueError(msg) from exc


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Mistral: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"Mistral: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_CHAT_COMPLETION: _build_chat_completion,
    OP_FIM_COMPLETION: _build_fim_completion,
    OP_CREATE_EMBEDDING: _build_create_embedding,
    OP_LIST_MODELS: _build_list_models,
}
