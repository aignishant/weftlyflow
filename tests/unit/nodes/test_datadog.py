"""Unit tests for :class:`DatadogNode`.

Exercises every supported operation against a respx-mocked Datadog
API. Verifies the distinctive dual ``DD-API-KEY`` + ``DD-APPLICATION-KEY``
header pair (application key omitted when empty), per-site host
derivation (us1, us3, eu1, gov, raw host), the v1 events flat body
shape, the v2 ``{"series": [{metric, type, points}]}`` envelope, the
inferred metric-type code, bindings/points coercion, and the
``errors: [...]`` error envelope.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import DatadogApiCredential
from weftlyflow.credentials.types.datadog_api import site_host_from
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.datadog import DatadogNode
from weftlyflow.nodes.integrations.datadog.operations import build_request

_CRED_ID: str = "cr_datadog"
_PROJECT_ID: str = "pr_test"
_API_KEY: str = "dd-api-key"
_APP_KEY: str = "dd-app-key"
_HOST: str = "https://api.datadoghq.com"


def _resolver(
    *,
    api_key: str = _API_KEY,
    application_key: str = _APP_KEY,
    site: str = "us1",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.datadog_api": DatadogApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.datadog_api",
                {
                    "api_key": api_key,
                    "application_key": application_key,
                    "site": site,
                },
                _PROJECT_ID,
            ),
        },
    )


def _ctx_for(
    node: Node,
    *,
    resolver: InMemoryCredentialResolver | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [], project_id=_PROJECT_ID)
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": []},
        credential_resolver=resolver or _resolver(),
    )


# --- post_event ------------------------------------------------------


@respx.mock
async def test_post_event_sends_dual_headers() -> None:
    route = respx.post(f"{_HOST}/api/v1/events").mock(
        return_value=Response(200, json={"event": {"id": 123}}),
    )
    node = Node(
        id="node_1",
        name="DD",
        type="weftlyflow.datadog",
        parameters={
            "operation": "post_event",
            "title": "Deploy",
            "text": "Shipping v1.2.3",
            "alert_type": "success",
            "priority": "normal",
            "tags": "env:prod,service:api",
        },
        credentials={"datadog_api": _CRED_ID},
    )
    await DatadogNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["DD-API-KEY"] == _API_KEY
    assert request.headers["DD-APPLICATION-KEY"] == _APP_KEY
    body = json.loads(request.content)
    assert body == {
        "title": "Deploy",
        "text": "Shipping v1.2.3",
        "alert_type": "success",
        "priority": "normal",
        "tags": ["env:prod", "service:api"],
    }


@respx.mock
async def test_post_event_omits_application_key_when_empty() -> None:
    route = respx.post(f"{_HOST}/api/v1/events").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="DD",
        type="weftlyflow.datadog",
        parameters={
            "operation": "post_event",
            "title": "x",
            "text": "y",
        },
        credentials={"datadog_api": _CRED_ID},
    )
    await DatadogNode().execute(
        _ctx_for(node, resolver=_resolver(application_key="")),
        [Item()],
    )
    assert "DD-APPLICATION-KEY" not in route.calls.last.request.headers


def test_post_event_rejects_invalid_alert_type() -> None:
    with pytest.raises(ValueError, match="alert_type"):
        build_request(
            "post_event",
            {"title": "t", "text": "x", "alert_type": "boom"},
        )


def test_post_event_requires_title() -> None:
    with pytest.raises(ValueError, match="'title' is required"):
        build_request("post_event", {"text": "x"})


# --- list_events -----------------------------------------------------


@respx.mock
async def test_list_events_query_params() -> None:
    route = respx.get(f"{_HOST}/api/v1/events").mock(
        return_value=Response(200, json={"events": []}),
    )
    node = Node(
        id="node_1",
        name="DD",
        type="weftlyflow.datadog",
        parameters={
            "operation": "list_events",
            "start": 1700000000,
            "end": 1700003600,
            "priority": "low",
            "tags": "env:prod",
        },
        credentials={"datadog_api": _CRED_ID},
    )
    await DatadogNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params.get("start") == "1700000000"
    assert params.get("end") == "1700003600"
    assert params.get("priority") == "low"
    assert params.get("tags") == "env:prod"


# --- get_monitor / list_monitors ------------------------------------


@respx.mock
async def test_get_monitor_hits_path() -> None:
    respx.get(f"{_HOST}/api/v1/monitor/42").mock(
        return_value=Response(200, json={"id": 42}),
    )
    node = Node(
        id="node_1",
        name="DD",
        type="weftlyflow.datadog",
        parameters={"operation": "get_monitor", "monitor_id": "42"},
        credentials={"datadog_api": _CRED_ID},
    )
    await DatadogNode().execute(_ctx_for(node), [Item()])


def test_list_monitors_page_size_caps() -> None:
    _, _, _, query = build_request(
        "list_monitors", {"page_size": 100_000},
    )
    assert query["page_size"] == 1_000


# --- query_metrics ---------------------------------------------------


@respx.mock
async def test_query_metrics_uses_from_to() -> None:
    route = respx.get(f"{_HOST}/api/v1/query").mock(
        return_value=Response(200, json={"series": []}),
    )
    node = Node(
        id="node_1",
        name="DD",
        type="weftlyflow.datadog",
        parameters={
            "operation": "query_metrics",
            "query": "avg:system.cpu.user{*}",
            "from_ts": 1700000000,
            "to_ts": 1700003600,
        },
        credentials={"datadog_api": _CRED_ID},
    )
    await DatadogNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params.get("from") == "1700000000"
    assert params.get("to") == "1700003600"
    assert params.get("query") == "avg:system.cpu.user{*}"


# --- submit_metric ---------------------------------------------------


@respx.mock
async def test_submit_metric_wraps_series_envelope() -> None:
    route = respx.post(f"{_HOST}/api/v2/series").mock(
        return_value=Response(202, json={}),
    )
    node = Node(
        id="node_1",
        name="DD",
        type="weftlyflow.datadog",
        parameters={
            "operation": "submit_metric",
            "metric": "my.app.latency",
            "metric_type": "gauge",
            "points": [{"timestamp": 1700000000, "value": 0.25}],
            "tags": "env:prod",
            "unit": "second",
        },
        credentials={"datadog_api": _CRED_ID},
    )
    await DatadogNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "series": [
            {
                "metric": "my.app.latency",
                "type": 3,
                "points": [{"timestamp": 1700000000, "value": 0.25}],
                "tags": ["env:prod"],
                "unit": "second",
            },
        ],
    }


def test_submit_metric_accepts_tuple_points() -> None:
    _, _, body, _ = build_request(
        "submit_metric",
        {
            "metric": "m",
            "metric_type": "count",
            "points": [[1700000000, 5]],
        },
    )
    assert body is not None
    assert body["series"][0]["type"] == 1
    assert body["series"][0]["points"] == [
        {"timestamp": 1700000000, "value": 5.0},
    ]


def test_submit_metric_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="metric_type"):
        build_request(
            "submit_metric",
            {"metric": "m", "metric_type": "distribution", "points": [[1, 1]]},
        )


def test_submit_metric_requires_points() -> None:
    with pytest.raises(ValueError, match="'points' is required"):
        build_request("submit_metric", {"metric": "m"})


# --- site host -------------------------------------------------------


def test_site_host_from_short_codes() -> None:
    assert site_host_from("us1") == "https://api.datadoghq.com"
    assert site_host_from("eu1") == "https://api.datadoghq.eu"
    assert site_host_from("gov") == "https://api.ddog-gov.com"


def test_site_host_from_full_host_passthrough() -> None:
    assert (
        site_host_from("api.us5.datadoghq.com")
        == "https://api.us5.datadoghq.com"
    )


def test_site_host_from_rejects_empty() -> None:
    with pytest.raises(ValueError, match="'site' is required"):
        site_host_from("   ")


def test_site_host_from_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match="unknown site"):
        site_host_from("moon")


# --- errors ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_errors_envelope() -> None:
    respx.post(f"{_HOST}/api/v1/events").mock(
        return_value=Response(
            400,
            json={"errors": ["missing title", "bad text"]},
        ),
    )
    node = Node(
        id="node_1",
        name="DD",
        type="weftlyflow.datadog",
        parameters={"operation": "post_event", "title": "t", "text": "x"},
        credentials={"datadog_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="missing title; bad text"):
        await DatadogNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="DD",
        type="weftlyflow.datadog",
        parameters={"operation": "post_event", "title": "t", "text": "x"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await DatadogNode().execute(_ctx_for(node), [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("delete_event", {})
