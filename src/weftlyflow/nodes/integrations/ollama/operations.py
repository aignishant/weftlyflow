"""Per-operation request builders for the Ollama node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to the Ollama base URL carried on the credential.

Distinctive Ollama shapes:

* Inference endpoints (``/api/generate``, ``/api/chat``, ``/api/embeddings``)
  all accept a ``stream`` flag; Weftlyflow forces ``stream=False`` so
  the node returns a single aggregated response per call.
* ``/api/tags`` is the canonical "list local models" endpoint — not
  ``/api/models`` as several other LLM vendors use.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.ollama.constants import (
    DEFAULT_MODEL,
    OP_CHAT,
    OP_EMBEDDINGS,
    OP_GENERATE,
    OP_LIST_MODELS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Ollama: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_generate(params: dict[str, Any]) -> RequestSpec:
    model = str(params.get("model") or DEFAULT_MODEL).strip()
    prompt = params.get("prompt")
    if prompt is None or (isinstance(prompt, str) and not prompt.strip()):
        msg = "Ollama: 'prompt' is required for generate"
        raise ValueError(msg)
    body: dict[str, Any] = {
        "model": model,
        "prompt": str(prompt),
        "stream": False,
    }
    system = str(params.get("system") or "").strip()
    if system:
        body["system"] = system
    fmt = str(params.get("format") or "").strip()
    if fmt:
        body["format"] = fmt
    options = params.get("options")
    if isinstance(options, dict) and options:
        body["options"] = options
    return "POST", "/api/generate", body, {}


def _build_chat(params: dict[str, Any]) -> RequestSpec:
    model = str(params.get("model") or DEFAULT_MODEL).strip()
    messages = _coerce_messages(params.get("messages"))
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    fmt = str(params.get("format") or "").strip()
    if fmt:
        body["format"] = fmt
    options = params.get("options")
    if isinstance(options, dict) and options:
        body["options"] = options
    return "POST", "/api/chat", body, {}


def _build_embeddings(params: dict[str, Any]) -> RequestSpec:
    model = str(params.get("model") or DEFAULT_MODEL).strip()
    prompt = params.get("prompt")
    if prompt is None or (isinstance(prompt, str) and not prompt.strip()):
        msg = "Ollama: 'prompt' is required for embeddings"
        raise ValueError(msg)
    body: dict[str, Any] = {"model": model, "prompt": str(prompt)}
    options = params.get("options")
    if isinstance(options, dict) and options:
        body["options"] = options
    return "POST", "/api/embeddings", body, {}


def _build_list_models(_: dict[str, Any]) -> RequestSpec:
    return "GET", "/api/tags", None, {}


def _coerce_messages(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        msg = "Ollama: 'messages' is required for chat"
        raise ValueError(msg)
    if not isinstance(raw, list) or not raw:
        msg = "Ollama: 'messages' must be a non-empty JSON array"
        raise ValueError(msg)
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = "Ollama: each message must be a JSON object"
            raise ValueError(msg)
        out.append(entry)
    return out


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GENERATE: _build_generate,
    OP_CHAT: _build_chat,
    OP_EMBEDDINGS: _build_embeddings,
    OP_LIST_MODELS: _build_list_models,
}
