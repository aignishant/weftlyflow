"""Prometheus counter/histogram registry.

One module owns every metric in the codebase so label cardinality and
naming stay consistent. Callers import a specific metric and emit against
it; they never create new metrics inline.

See IMPLEMENTATION_BIBLE.md §19.2 for the canonical list.

The metrics are registered against the global default registry so
``prometheus_client.generate_latest()`` picks them up without extra
wiring. Tests that need an isolated registry can use
``prometheus_client.CollectorRegistry`` via the ``registry`` kwarg on
the metric constructors, but this module intentionally does not expose
that override — a single process should have exactly one live view.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

__all__ = [
    "CONTENT_TYPE_LATEST",
    "REGISTRY",
    "active_workflows",
    "execution_duration_seconds",
    "executions_total",
    "expression_evaluations_total",
    "http_requests_total",
    "node_duration_seconds",
    "render_latest",
    "webhook_requests_total",
]

# A dedicated registry keeps Weftlyflow's metrics isolated from any third
# party that scrapes the default registry in the same process.
REGISTRY: CollectorRegistry = CollectorRegistry(auto_describe=True)

executions_total: Counter = Counter(
    "weftlyflow_executions_total",
    "Count of workflow executions by terminal status and trigger mode.",
    labelnames=("status", "mode"),
    registry=REGISTRY,
)

execution_duration_seconds: Histogram = Histogram(
    "weftlyflow_execution_duration_seconds",
    "End-to-end workflow execution duration in seconds.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0, 1800.0),
    registry=REGISTRY,
)

node_duration_seconds: Histogram = Histogram(
    "weftlyflow_node_duration_seconds",
    "Per-node execution duration in seconds.",
    labelnames=("node_type",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

webhook_requests_total: Counter = Counter(
    "weftlyflow_webhook_requests_total",
    "Inbound webhook requests by HTTP method and outcome.",
    labelnames=("method", "outcome"),
    registry=REGISTRY,
)

http_requests_total: Counter = Counter(
    "weftlyflow_http_requests_total",
    "API requests by route template and HTTP status.",
    labelnames=("route", "status"),
    registry=REGISTRY,
)

active_workflows: Gauge = Gauge(
    "weftlyflow_active_workflows",
    "Number of workflows currently flagged active.",
    registry=REGISTRY,
)

expression_evaluations_total: Counter = Counter(
    "weftlyflow_expression_evaluations_total",
    "Expression-engine evaluations by outcome.",
    labelnames=("outcome",),
    registry=REGISTRY,
)


def render_latest() -> tuple[bytes, str]:
    """Return ``(body, content_type)`` for the ``/metrics`` endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
