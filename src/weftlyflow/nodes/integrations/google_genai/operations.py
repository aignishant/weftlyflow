"""Per-operation request builders for the Google GenAI node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://generativelanguage.googleapis.com``.

Distinctive Gemini shapes (vs OpenAI/Anthropic):

* Content is carried under ``contents`` (not ``messages``) as a list of
  ``{"role": ..., "parts": [{"text": ...}]}`` objects — parts can be
  text, inline data, or tool calls.
* Sampling controls live under a nested ``generationConfig`` block
  (``temperature``, ``maxOutputTokens``, ``topP``, ``topK``).
* System prompts use the top-level ``systemInstruction`` field rather
  than a leading message with role ``system``.
* Model + action are fused into the URL (``:generateContent``,
  ``:countTokens``) rather than separated by path and body.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.google_genai.constants import (
    DEFAULT_MODEL,
    OP_COUNT_TOKENS,
    OP_GENERATE_CONTENT,
    OP_GET_MODEL,
    OP_LIST_MODELS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]

_GENERATION_CONFIG_KEYS: tuple[tuple[str, str, str], ...] = (
    # (param_name, body_key, kind)  — kind is "int" or "float".
    ("max_output_tokens", "maxOutputTokens", "int"),
    ("temperature", "temperature", "float"),
    ("top_p", "topP", "float"),
    ("top_k", "topK", "int"),
)


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Google GenAI: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_generate_content(params: dict[str, Any]) -> RequestSpec:
    model = _resolve_model(params)
    contents = _coerce_contents(params.get("contents"))
    body: dict[str, Any] = {"contents": contents}
    system = str(params.get("system") or "").strip()
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    generation_config = _build_generation_config(params)
    if generation_config:
        body["generationConfig"] = generation_config
    safety = params.get("safety_settings")
    if isinstance(safety, list) and safety:
        body["safetySettings"] = safety
    path = f"/v1beta/models/{quote(model, safe='')}:generateContent"
    return "POST", path, body, {}


def _build_count_tokens(params: dict[str, Any]) -> RequestSpec:
    model = _resolve_model(params)
    contents = _coerce_contents(params.get("contents"))
    body: dict[str, Any] = {"contents": contents}
    path = f"/v1beta/models/{quote(model, safe='')}:countTokens"
    return "POST", path, body, {}


def _build_list_models(_: dict[str, Any]) -> RequestSpec:
    return "GET", "/v1beta/models", None, {}


def _build_get_model(params: dict[str, Any]) -> RequestSpec:
    model_id = _required(params, "model_id")
    return "GET", f"/v1beta/models/{quote(model_id, safe='')}", None, {}


def _resolve_model(params: dict[str, Any]) -> str:
    model = str(params.get("model") or DEFAULT_MODEL).strip()
    if not model:
        msg = "Google GenAI: 'model' must not be empty"
        raise ValueError(msg)
    # Gemini accepts either bare ``gemini-1.5-flash`` or the fully-qualified
    # ``models/gemini-1.5-flash``. Strip the prefix so the URL stays tidy.
    return model.removeprefix("models/")


def _coerce_contents(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        msg = "Google GenAI: 'contents' is required"
        raise ValueError(msg)
    if not isinstance(raw, list) or not raw:
        msg = "Google GenAI: 'contents' must be a non-empty JSON array"
        raise ValueError(msg)
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = "Google GenAI: each content entry must be a JSON object"
            raise ValueError(msg)
        out.append(entry)
    return out


def _build_generation_config(params: dict[str, Any]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for param_name, body_key, kind in _GENERATION_CONFIG_KEYS:
        raw = params.get(param_name)
        if raw in (None, ""):
            continue
        config[body_key] = (
            _coerce_positive_int(raw, field=param_name)
            if kind == "int"
            else _coerce_float(raw, field=param_name)
        )
    return config


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Google GenAI: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"Google GenAI: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


def _coerce_float(raw: Any, *, field: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Google GenAI: {field!r} must be a number"
        raise ValueError(msg) from exc


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Google GenAI: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GENERATE_CONTENT: _build_generate_content,
    OP_COUNT_TOKENS: _build_count_tokens,
    OP_LIST_MODELS: _build_list_models,
    OP_GET_MODEL: _build_get_model,
}
