"""Per-operation request builders for the Datadog node.

Each builder returns ``(http_method, path, body, query)``. Paths are
mounted under the per-site host (e.g.
``https://api.datadoghq.com``) resolved from the credential.

Shape quirks worth noting:

* ``post_event`` (v1) takes a flat JSON body with ``title`` + ``text``
  and a free-form ``tags`` list.
* ``query_metrics`` (v1) is a GET with unix-second ``from``/``to`` +
  a ``query`` string DSL (e.g. ``avg:system.cpu.user{*}``).
* ``submit_metric`` uses the v2 ``/api/v2/series`` shape with a
  ``{"series": [{metric, type, points: [{timestamp, value}]}]}``
  envelope.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.datadog.constants import (
    DEFAULT_MONITOR_PAGE_SIZE,
    MAX_MONITOR_PAGE_SIZE,
    OP_GET_MONITOR,
    OP_LIST_EVENTS,
    OP_LIST_MONITORS,
    OP_POST_EVENT,
    OP_QUERY_METRICS,
    OP_SUBMIT_METRIC,
    VALID_ALERT_TYPES,
    VALID_PRIORITIES,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]

_METRIC_TYPES: dict[str, int] = {
    "unspecified": 0,
    "count": 1,
    "rate": 2,
    "gauge": 3,
}
_POINT_TUPLE_LEN: int = 2


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Datadog: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_post_event(params: dict[str, Any]) -> RequestSpec:
    title = _required(params, "title")
    text = _required(params, "text")
    body: dict[str, Any] = {"title": title, "text": text}
    alert_type = str(params.get("alert_type") or "").strip().lower()
    if alert_type:
        if alert_type not in VALID_ALERT_TYPES:
            msg = (
                f"Datadog: 'alert_type' must be one of "
                f"{sorted(VALID_ALERT_TYPES)!r}"
            )
            raise ValueError(msg)
        body["alert_type"] = alert_type
    priority = str(params.get("priority") or "").strip().lower()
    if priority:
        if priority not in VALID_PRIORITIES:
            msg = (
                f"Datadog: 'priority' must be one of {sorted(VALID_PRIORITIES)!r}"
            )
            raise ValueError(msg)
        body["priority"] = priority
    tags = _coerce_string_list(params.get("tags"), field="tags")
    if tags:
        body["tags"] = tags
    source = str(params.get("source_type_name") or "").strip()
    if source:
        body["source_type_name"] = source
    aggregation_key = str(params.get("aggregation_key") or "").strip()
    if aggregation_key:
        body["aggregation_key"] = aggregation_key
    return "POST", "/api/v1/events", body, {}


def _build_list_events(params: dict[str, Any]) -> RequestSpec:
    start = _required_int(params, "start")
    end = _required_int(params, "end")
    query: dict[str, Any] = {"start": start, "end": end}
    priority = str(params.get("priority") or "").strip().lower()
    if priority:
        if priority not in VALID_PRIORITIES:
            msg = (
                f"Datadog: 'priority' must be one of {sorted(VALID_PRIORITIES)!r}"
            )
            raise ValueError(msg)
        query["priority"] = priority
    sources = str(params.get("sources") or "").strip()
    if sources:
        query["sources"] = sources
    tags = _coerce_string_list(params.get("tags"), field="tags")
    if tags:
        query["tags"] = ",".join(tags)
    unaggregated = params.get("unaggregated")
    if unaggregated is not None and unaggregated != "":
        query["unaggregated"] = "true" if _coerce_bool(unaggregated) else "false"
    return "GET", "/api/v1/events", None, query


def _build_get_monitor(params: dict[str, Any]) -> RequestSpec:
    monitor_id = _required(params, "monitor_id")
    query: dict[str, Any] = {}
    group_states = str(params.get("group_states") or "").strip()
    if group_states:
        query["group_states"] = group_states
    return "GET", f"/api/v1/monitor/{quote(monitor_id, safe='')}", None, query


def _build_list_monitors(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {
        "page_size": _coerce_page_size(params.get("page_size")),
    }
    page = params.get("page")
    if page is not None and page != "":
        query["page"] = _coerce_non_negative_int(page, field="page")
    name = str(params.get("name") or "").strip()
    if name:
        query["name"] = name
    tags = _coerce_string_list(params.get("monitor_tags"), field="monitor_tags")
    if tags:
        query["monitor_tags"] = ",".join(tags)
    return "GET", "/api/v1/monitor", None, query


def _build_query_metrics(params: dict[str, Any]) -> RequestSpec:
    query_text = _required(params, "query")
    from_ts = _required_int(params, "from_ts")
    to_ts = _required_int(params, "to_ts")
    query: dict[str, Any] = {
        "query": query_text,
        "from": from_ts,
        "to": to_ts,
    }
    return "GET", "/api/v1/query", None, query


def _build_submit_metric(params: dict[str, Any]) -> RequestSpec:
    metric = _required(params, "metric")
    points = _coerce_points(params.get("points"))
    metric_type = str(params.get("metric_type") or "gauge").strip().lower()
    if metric_type not in _METRIC_TYPES:
        msg = (
            f"Datadog: 'metric_type' must be one of "
            f"{sorted(_METRIC_TYPES)!r}"
        )
        raise ValueError(msg)
    series: dict[str, Any] = {
        "metric": metric,
        "type": _METRIC_TYPES[metric_type],
        "points": points,
    }
    tags = _coerce_string_list(params.get("tags"), field="tags")
    if tags:
        series["tags"] = tags
    unit = str(params.get("unit") or "").strip()
    if unit:
        series["unit"] = unit
    body: dict[str, Any] = {"series": [series]}
    return "POST", "/api/v2/series", body, {}


def _coerce_points(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        msg = "Datadog: 'points' is required"
        raise ValueError(msg)
    if not isinstance(raw, list) or not raw:
        msg = "Datadog: 'points' must be a non-empty list"
        raise ValueError(msg)
    normalized: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, dict):
            timestamp = entry.get("timestamp")
            value = entry.get("value")
        elif isinstance(entry, (list, tuple)) and len(entry) == _POINT_TUPLE_LEN:
            timestamp, value = entry
        else:
            msg = (
                "Datadog: each point must be {'timestamp','value'} or "
                "[timestamp, value]"
            )
            raise ValueError(msg)
        normalized.append(
            {
                "timestamp": _coerce_non_negative_int(
                    timestamp, field="point.timestamp",
                ),
                "value": _coerce_float(value, field="point.value"),
            },
        )
    return normalized


def _coerce_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    msg = f"Datadog: boolean flag must be true/false, got {raw!r}"
    raise ValueError(msg)


def _coerce_non_negative_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Datadog: {field!r} must be a non-negative integer"
        raise ValueError(msg) from exc
    return max(0, value)


def _coerce_float(raw: Any, *, field: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Datadog: {field!r} must be numeric"
        raise ValueError(msg) from exc


def _coerce_page_size(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_MONITOR_PAGE_SIZE
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Datadog: 'page_size' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Datadog: 'page_size' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_MONITOR_PAGE_SIZE)


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Datadog: {field!r} must be a string or list of strings"
    raise ValueError(msg)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Datadog: {key!r} is required"
        raise ValueError(msg)
    return value


def _required_int(params: dict[str, Any], key: str) -> int:
    raw = params.get(key)
    if raw is None or raw == "":
        msg = f"Datadog: {key!r} is required"
        raise ValueError(msg)
    return _coerce_non_negative_int(raw, field=key)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_POST_EVENT: _build_post_event,
    OP_LIST_EVENTS: _build_list_events,
    OP_GET_MONITOR: _build_get_monitor,
    OP_LIST_MONITORS: _build_list_monitors,
    OP_QUERY_METRICS: _build_query_metrics,
    OP_SUBMIT_METRIC: _build_submit_metric,
}
