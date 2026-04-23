"""Per-operation request builders for the Snowflake SQL API node.

Each builder returns ``(http_method, path, body, query)``. The node
layer prefixes with the per-account host
``https://<account>.snowflakecomputing.com`` and the ``/api/v2`` root.

The distinctive shape is the ``execute`` body — Snowflake's SQL API
accepts ``statement`` as a plain string and returns a statement handle
when ``ASYNC=true``, or paginated result rows when the query finishes
within the configured timeout. Bind parameters are sent as a
positional dict keyed ``"1"``, ``"2"``, … with ``{type, value}``
shape.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.snowflake.constants import (
    DEFAULT_FETCH_ROWS,
    MAX_FETCH_ROWS,
    OP_CANCEL,
    OP_EXECUTE,
    OP_GET_STATUS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Snowflake: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_execute(params: dict[str, Any]) -> RequestSpec:
    statement = _required(params, "statement")
    body: dict[str, Any] = {"statement": statement}
    warehouse = str(params.get("warehouse") or "").strip()
    if warehouse:
        body["warehouse"] = warehouse
    database = str(params.get("database") or "").strip()
    if database:
        body["database"] = database
    schema = str(params.get("schema") or "").strip()
    if schema:
        body["schema"] = schema
    role = str(params.get("role") or "").strip()
    if role:
        body["role"] = role
    timeout = params.get("timeout")
    if timeout is not None and timeout != "":
        body["timeout"] = _coerce_non_negative_int(timeout, field="timeout")
    bindings = params.get("bindings")
    if bindings is not None:
        body["bindings"] = _coerce_bindings(bindings)
    query: dict[str, Any] = {}
    if _coerce_bool(params.get("async_exec")):
        query["async"] = "true"
    request_id = str(params.get("request_id") or "").strip()
    if request_id:
        query["requestId"] = request_id
    return "POST", "/api/v2/statements", body, query


def _build_get_status(params: dict[str, Any]) -> RequestSpec:
    handle = _required(params, "statement_handle")
    query: dict[str, Any] = {}
    partition = params.get("partition")
    if partition is not None and partition != "":
        query["partition"] = _coerce_non_negative_int(
            partition, field="partition",
        )
    page_size = params.get("page_size")
    if page_size not in (None, ""):
        query["pageSize"] = _coerce_fetch_rows(page_size)
    return "GET", f"/api/v2/statements/{quote(handle, safe='')}", None, query


def _build_cancel(params: dict[str, Any]) -> RequestSpec:
    handle = _required(params, "statement_handle")
    path = f"/api/v2/statements/{quote(handle, safe='')}/cancel"
    return "POST", path, None, {}


def _coerce_bindings(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        msg = "Snowflake: 'bindings' must be a JSON object keyed by position"
        raise ValueError(msg)
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        str_key = str(key).strip()
        if not str_key:
            msg = "Snowflake: bindings keys must be non-empty strings"
            raise ValueError(msg)
        if isinstance(value, dict):
            if "type" not in value or "value" not in value:
                msg = (
                    "Snowflake: each binding must be a {'type', 'value'} "
                    "pair"
                )
                raise ValueError(msg)
            normalized[str_key] = {
                "type": str(value["type"]),
                "value": _stringify(value["value"]),
            }
        else:
            normalized[str_key] = {
                "type": _infer_type(value),
                "value": _stringify(value),
            }
    return normalized


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "FIXED"
    if isinstance(value, float):
        return "REAL"
    return "TEXT"


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _coerce_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw in (None, ""):
        return False
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    msg = f"Snowflake: boolean flag must be true/false, got {raw!r}"
    raise ValueError(msg)


def _coerce_non_negative_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Snowflake: {field!r} must be a non-negative integer"
        raise ValueError(msg) from exc
    return max(0, value)


def _coerce_fetch_rows(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_FETCH_ROWS
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Snowflake: 'page_size' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Snowflake: 'page_size' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_FETCH_ROWS)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Snowflake: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_EXECUTE: _build_execute,
    OP_GET_STATUS: _build_get_status,
    OP_CANCEL: _build_cancel,
}
