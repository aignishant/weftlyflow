"""Constants for the Datadog integration node.

Reference: https://docs.datadoghq.com/api/latest/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

OP_POST_EVENT: Final[str] = "post_event"
OP_LIST_EVENTS: Final[str] = "list_events"
OP_GET_MONITOR: Final[str] = "get_monitor"
OP_LIST_MONITORS: Final[str] = "list_monitors"
OP_QUERY_METRICS: Final[str] = "query_metrics"
OP_SUBMIT_METRIC: Final[str] = "submit_metric"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_POST_EVENT,
    OP_LIST_EVENTS,
    OP_GET_MONITOR,
    OP_LIST_MONITORS,
    OP_QUERY_METRICS,
    OP_SUBMIT_METRIC,
)

VALID_ALERT_TYPES: Final[frozenset[str]] = frozenset(
    {"error", "warning", "info", "success", "user_update", "recommendation", "snapshot"},
)
VALID_PRIORITIES: Final[frozenset[str]] = frozenset({"normal", "low"})

DEFAULT_MONITOR_PAGE_SIZE: Final[int] = 100
MAX_MONITOR_PAGE_SIZE: Final[int] = 1_000
