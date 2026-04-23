"""Per-operation request builders for the Anthropic node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://api.anthropic.com``.

Distinctive Anthropic shapes:

* ``create_message`` requires both ``model`` and ``max_tokens`` — the
  builder defaults ``max_tokens`` to 1024 if omitted (Anthropic requires
  it explicitly, unlike OpenAI which has a server-side default).
* ``count_tokens`` is a free, separate ``/v1/messages/count_tokens``
  endpoint — distinct from OpenAI which has no equivalent.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.anthropic.constants import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    OP_COUNT_TOKENS,
    OP_CREATE_MESSAGE,
    OP_GET_MODEL,
    OP_LIST_MODELS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Anthropic: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_create_message(params: dict[str, Any]) -> RequestSpec:
    model = str(params.get("model") or DEFAULT_MODEL).strip()
    messages = _coerce_messages(params.get("messages"))
    max_tokens = params.get("max_tokens")
    max_tokens_int = (
        _coerce_positive_int(max_tokens, field="max_tokens")
        if max_tokens not in (None, "")
        else DEFAULT_MAX_TOKENS
    )
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens_int,
    }
    system = str(params.get("system") or "").strip()
    if system:
        body["system"] = system
    temperature = params.get("temperature")
    if temperature not in (None, ""):
        body["temperature"] = _coerce_float(temperature, field="temperature")
    metadata = params.get("metadata")
    if isinstance(metadata, dict) and metadata:
        body["metadata"] = metadata
    return "POST", "/v1/messages", body, {}


def _build_count_tokens(params: dict[str, Any]) -> RequestSpec:
    model = str(params.get("model") or DEFAULT_MODEL).strip()
    messages = _coerce_messages(params.get("messages"))
    body: dict[str, Any] = {"model": model, "messages": messages}
    system = str(params.get("system") or "").strip()
    if system:
        body["system"] = system
    return "POST", "/v1/messages/count_tokens", body, {}


def _build_list_models(_: dict[str, Any]) -> RequestSpec:
    return "GET", "/v1/models", None, {}


def _build_get_model(params: dict[str, Any]) -> RequestSpec:
    model_id = _required(params, "model_id")
    return "GET", f"/v1/models/{quote(model_id, safe='')}", None, {}


def _coerce_messages(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        msg = "Anthropic: 'messages' is required"
        raise ValueError(msg)
    if not isinstance(raw, list) or not raw:
        msg = "Anthropic: 'messages' must be a non-empty JSON array"
        raise ValueError(msg)
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = "Anthropic: each message must be a JSON object"
            raise ValueError(msg)
        out.append(entry)
    return out


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Anthropic: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"Anthropic: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


def _coerce_float(raw: Any, *, field: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Anthropic: {field!r} must be a number"
        raise ValueError(msg) from exc


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Anthropic: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_CREATE_MESSAGE: _build_create_message,
    OP_COUNT_TOKENS: _build_count_tokens,
    OP_LIST_MODELS: _build_list_models,
    OP_GET_MODEL: _build_get_model,
}
