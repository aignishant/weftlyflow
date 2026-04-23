"""Per-operation request builders for the Elasticsearch node.

Each builder returns ``(http_method, path, body, query_params,
content_type)``. Most Elasticsearch endpoints speak standard JSON, but
``POST /_bulk`` requires ``application/x-ndjson`` where every action
metadata and every document live on separate newline-terminated
lines. The builder flattens a caller-supplied list of ``{action, doc}``
pairs into that wire format.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.elasticsearch.constants import (
    DEFAULT_SEARCH_SIZE,
    MAX_SEARCH_SIZE,
    OP_BULK,
    OP_DELETE,
    OP_GET,
    OP_INDEX,
    OP_SEARCH,
    OP_UPDATE,
)

_JSON: str = "application/json"
_NDJSON: str = "application/x-ndjson"

RequestSpec = tuple[str, str, Any, dict[str, Any], str]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Elasticsearch: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_search(params: dict[str, Any]) -> RequestSpec:
    index = _required(params, "index")
    query = params.get("query")
    body: dict[str, Any] = {"size": _coerce_size(params.get("size"))}
    if query not in (None, "", {}):
        if not isinstance(query, dict):
            msg = "Elasticsearch: 'query' must be a JSON object"
            raise ValueError(msg)
        body["query"] = dict(query)
    else:
        body["query"] = {"match_all": {}}
    from_offset = params.get("from_")
    if from_offset not in (None, ""):
        body["from"] = _coerce_non_negative(from_offset, field="from_")
    sort = params.get("sort")
    if sort not in (None, "", []):
        body["sort"] = sort
    return "POST", f"/{quote(index, safe='')}/_search", body, {}, _JSON


def _build_index(params: dict[str, Any]) -> RequestSpec:
    index = _required(params, "index")
    document = params.get("document")
    if not isinstance(document, dict) or not document:
        msg = "Elasticsearch: 'document' must be a non-empty JSON object"
        raise ValueError(msg)
    doc_id = str(params.get("id") or "").strip()
    refresh = _coerce_refresh(params.get("refresh"))
    query: dict[str, Any] = {}
    if refresh is not None:
        query["refresh"] = refresh
    if doc_id:
        path = f"/{quote(index, safe='')}/_doc/{quote(doc_id, safe='')}"
        return "PUT", path, dict(document), query, _JSON
    return "POST", f"/{quote(index, safe='')}/_doc", dict(document), query, _JSON


def _build_get(params: dict[str, Any]) -> RequestSpec:
    index = _required(params, "index")
    doc_id = _required(params, "id")
    path = f"/{quote(index, safe='')}/_doc/{quote(doc_id, safe='')}"
    return "GET", path, None, {}, _JSON


def _build_update(params: dict[str, Any]) -> RequestSpec:
    index = _required(params, "index")
    doc_id = _required(params, "id")
    doc = params.get("document")
    script = params.get("script")
    body: dict[str, Any] = {}
    if isinstance(doc, dict) and doc:
        body["doc"] = dict(doc)
    if isinstance(script, dict) and script:
        body["script"] = dict(script)
    if not body:
        msg = "Elasticsearch: update requires 'document' or 'script'"
        raise ValueError(msg)
    query: dict[str, Any] = {}
    refresh = _coerce_refresh(params.get("refresh"))
    if refresh is not None:
        query["refresh"] = refresh
    path = f"/{quote(index, safe='')}/_update/{quote(doc_id, safe='')}"
    return "POST", path, body, query, _JSON


def _build_delete(params: dict[str, Any]) -> RequestSpec:
    index = _required(params, "index")
    doc_id = _required(params, "id")
    query: dict[str, Any] = {}
    refresh = _coerce_refresh(params.get("refresh"))
    if refresh is not None:
        query["refresh"] = refresh
    path = f"/{quote(index, safe='')}/_doc/{quote(doc_id, safe='')}"
    return "DELETE", path, None, query, _JSON


def _build_bulk(params: dict[str, Any]) -> RequestSpec:
    index = str(params.get("index") or "").strip()
    actions = params.get("actions")
    if not isinstance(actions, list) or not actions:
        msg = "Elasticsearch: 'actions' must be a non-empty list"
        raise ValueError(msg)
    lines: list[str] = []
    for entry in actions:
        if not isinstance(entry, dict):
            msg = "Elasticsearch: every bulk action must be a JSON object"
            raise ValueError(msg)
        action = entry.get("action")
        if not isinstance(action, dict) or not action:
            msg = "Elasticsearch: bulk entry missing 'action' object"
            raise ValueError(msg)
        lines.append(json.dumps(action, separators=(",", ":")))
        document = entry.get("doc")
        if document is not None:
            if not isinstance(document, dict):
                msg = "Elasticsearch: bulk 'doc' must be a JSON object"
                raise ValueError(msg)
            lines.append(json.dumps(document, separators=(",", ":")))
    body = "\n".join(lines) + "\n"
    path = f"/{quote(index, safe='')}/_bulk" if index else "/_bulk"
    return "POST", path, body, {}, _NDJSON


def _coerce_size(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_SEARCH_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Elasticsearch: 'size' must be an integer"
        raise ValueError(msg) from exc
    if value < 0:
        msg = "Elasticsearch: 'size' must be >= 0"
        raise ValueError(msg)
    return min(value, MAX_SEARCH_SIZE)


def _coerce_non_negative(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Elasticsearch: {field!r} must be an integer"
        raise ValueError(msg) from exc
    if value < 0:
        msg = f"Elasticsearch: {field!r} must be >= 0"
        raise ValueError(msg)
    return value


def _coerce_refresh(raw: Any) -> str | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, bool):
        return "true" if raw else "false"
    text = str(raw).strip().lower()
    if text not in {"true", "false", "wait_for"}:
        msg = "Elasticsearch: 'refresh' must be 'true', 'false', or 'wait_for'"
        raise ValueError(msg)
    return text


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Elasticsearch: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_SEARCH: _build_search,
    OP_INDEX: _build_index,
    OP_GET: _build_get,
    OP_UPDATE: _build_update,
    OP_DELETE: _build_delete,
    OP_BULK: _build_bulk,
}
