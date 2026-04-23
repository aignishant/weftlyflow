"""Per-operation request builders for the OpenAI node.

Each builder returns ``(http_method, path, body, query)``. Paths are
prefixed with the ``/v1`` root already baked into the API base URL.

Body shapes of note:

* ``chat_completion`` expects a ``messages`` list of
  ``{"role", "content"}`` dicts and honors optional ``temperature``,
  ``top_p``, ``max_tokens``, ``response_format``, ``tools``, and
  ``stream`` (the node intentionally forces ``stream=false`` because
  Weftlyflow nodes return a single item).
* ``create_embedding`` accepts ``input`` as a string or a list of
  strings and returns one embedding vector per input entry.
* ``create_image`` posts ``prompt`` + ``size`` + optional ``n``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.openai.constants import (
    OP_CHAT_COMPLETION,
    OP_CREATE_EMBEDDING,
    OP_CREATE_IMAGE,
    OP_CREATE_MODERATION,
    OP_GET_MODEL,
    OP_LIST_MODELS,
    VALID_IMAGE_SIZES,
    VALID_RESPONSE_FORMATS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"OpenAI: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_chat_completion(params: dict[str, Any]) -> RequestSpec:
    model = _required(params, "model")
    messages = _coerce_messages(params.get("messages"))
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
    for key in ("temperature", "top_p"):
        value = params.get(key)
        if value is not None and value != "":
            body[key] = _coerce_float(value, field=key)
    max_tokens = params.get("max_tokens")
    if max_tokens is not None and max_tokens != "":
        body["max_tokens"] = _coerce_positive_int(max_tokens, field="max_tokens")
    response_format = str(params.get("response_format") or "").strip()
    if response_format:
        if response_format not in {"text", "json_object"}:
            msg = "OpenAI: 'response_format' must be 'text' or 'json_object'"
            raise ValueError(msg)
        body["response_format"] = {"type": response_format}
    tools = params.get("tools")
    if tools is not None and tools != "":
        if not isinstance(tools, list):
            msg = "OpenAI: 'tools' must be a JSON array"
            raise ValueError(msg)
        body["tools"] = tools
    return "POST", "/v1/chat/completions", body, {}


def _build_create_embedding(params: dict[str, Any]) -> RequestSpec:
    model = _required(params, "model")
    raw_input = params.get("input")
    if raw_input is None or raw_input == "":
        msg = "OpenAI: 'input' is required"
        raise ValueError(msg)
    body: dict[str, Any] = {"model": model, "input": raw_input}
    dimensions = params.get("dimensions")
    if dimensions is not None and dimensions != "":
        body["dimensions"] = _coerce_positive_int(dimensions, field="dimensions")
    return "POST", "/v1/embeddings", body, {}


def _build_list_models(params: dict[str, Any]) -> RequestSpec:
    del params
    return "GET", "/v1/models", None, {}


def _build_get_model(params: dict[str, Any]) -> RequestSpec:
    model = _required(params, "model")
    return "GET", f"/v1/models/{quote(model, safe='')}", None, {}


def _build_create_moderation(params: dict[str, Any]) -> RequestSpec:
    raw_input = params.get("input")
    if raw_input is None or raw_input == "":
        msg = "OpenAI: 'input' is required"
        raise ValueError(msg)
    body: dict[str, Any] = {"input": raw_input}
    model = str(params.get("model") or "").strip()
    if model:
        body["model"] = model
    return "POST", "/v1/moderations", body, {}


def _build_create_image(params: dict[str, Any]) -> RequestSpec:
    prompt = _required(params, "prompt")
    body: dict[str, Any] = {"prompt": prompt}
    model = str(params.get("model") or "").strip()
    if model:
        body["model"] = model
    size = str(params.get("size") or "").strip()
    if size:
        if size not in VALID_IMAGE_SIZES:
            msg = (
                f"OpenAI: 'size' must be one of {sorted(VALID_IMAGE_SIZES)!r}"
            )
            raise ValueError(msg)
        body["size"] = size
    n = params.get("n")
    if n is not None and n != "":
        body["n"] = _coerce_positive_int(n, field="n")
    response_format = str(params.get("response_format") or "").strip()
    if response_format:
        if response_format not in VALID_RESPONSE_FORMATS:
            msg = (
                f"OpenAI: 'response_format' must be one of "
                f"{sorted(VALID_RESPONSE_FORMATS)!r}"
            )
            raise ValueError(msg)
        body["response_format"] = response_format
    return "POST", "/v1/images/generations", body, {}


def _coerce_messages(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        msg = "OpenAI: 'messages' is required"
        raise ValueError(msg)
    if not isinstance(raw, list) or not raw:
        msg = "OpenAI: 'messages' must be a non-empty list"
        raise ValueError(msg)
    normalized: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = "OpenAI: each message must be an object with 'role' and 'content'"
            raise ValueError(msg)
        role = str(entry.get("role") or "").strip()
        if not role:
            msg = "OpenAI: message is missing 'role'"
            raise ValueError(msg)
        if "content" not in entry:
            msg = "OpenAI: message is missing 'content'"
            raise ValueError(msg)
        normalized.append({**entry, "role": role})
    return normalized


def _coerce_float(raw: Any, *, field: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        msg = f"OpenAI: {field!r} must be numeric"
        raise ValueError(msg) from exc


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"OpenAI: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"OpenAI: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"OpenAI: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_CHAT_COMPLETION: _build_chat_completion,
    OP_CREATE_EMBEDDING: _build_create_embedding,
    OP_LIST_MODELS: _build_list_models,
    OP_GET_MODEL: _build_get_model,
    OP_CREATE_MODERATION: _build_create_moderation,
    OP_CREATE_IMAGE: _build_create_image,
}
