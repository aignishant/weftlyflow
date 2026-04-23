"""Unit tests for :class:`Ga4Node` and ``Ga4MeasurementCredential``.

GA4's Measurement Protocol authenticates via two query parameters
(``measurement_id`` + ``api_secret``) on every request; there is no
``Authorization`` header. The credential appends both via
``url.copy_merge_params`` and the node routes between the production
``/mp/collect`` and debug ``/debug/mp/collect`` paths.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import Ga4MeasurementCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.ga4 import Ga4Node
from weftlyflow.nodes.integrations.ga4.operations import build_request

_CRED_ID: str = "cr_ga4"
_PROJECT_ID: str = "pr_test"
_MEASUREMENT_ID: str = "G-ABCDEF1234"
_API_SECRET: str = "s3cr3t_abc"
_API: str = "https://www.google-analytics.com"
_CLIENT_ID: str = "cid.weftlyflow.1"


def _resolver(
    *, measurement_id: str = _MEASUREMENT_ID, api_secret: str = _API_SECRET,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.ga4_measurement": Ga4MeasurementCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.ga4_measurement",
                {"measurement_id": measurement_id, "api_secret": api_secret},
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


# --- credential: dual-query-param auth ----------------------------


async def test_credential_inject_appends_both_query_params() -> None:
    request = httpx.Request("POST", f"{_API}/mp/collect")
    out = await Ga4MeasurementCredential().inject(
        {"measurement_id": _MEASUREMENT_ID, "api_secret": _API_SECRET}, request,
    )
    assert out.url.params["measurement_id"] == _MEASUREMENT_ID
    assert out.url.params["api_secret"] == _API_SECRET
    # No Authorization header ever set.
    assert "Authorization" not in out.headers


# --- track_event ---------------------------------------------------


@respx.mock
async def test_track_event_posts_to_mp_collect_with_single_event() -> None:
    route = respx.post(f"{_API}/mp/collect").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="GA4",
        type="weftlyflow.ga4",
        parameters={
            "operation": "track_event",
            "client_id": _CLIENT_ID,
            "event_name": "sign_up",
            "event_params": {"method": "email"},
        },
        credentials={"ga4_measurement": _CRED_ID},
    )
    await Ga4Node().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    assert sent.url.params["measurement_id"] == _MEASUREMENT_ID
    assert sent.url.params["api_secret"] == _API_SECRET
    body = json.loads(sent.content)
    assert body["client_id"] == _CLIENT_ID
    assert body["events"] == [{"name": "sign_up", "params": {"method": "email"}}]


def test_track_event_requires_event_name() -> None:
    with pytest.raises(ValueError, match="'event_name' is required"):
        build_request("track_event", {"client_id": _CLIENT_ID})


def test_track_event_requires_client_id() -> None:
    with pytest.raises(ValueError, match="'client_id' is required"):
        build_request("track_event", {"event_name": "sign_up"})


# --- track_events (batch) ------------------------------------------


@respx.mock
async def test_track_events_batches_multiple_events() -> None:
    route = respx.post(f"{_API}/mp/collect").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="GA4",
        type="weftlyflow.ga4",
        parameters={
            "operation": "track_events",
            "client_id": _CLIENT_ID,
            "user_id": "u_42",
            "events": [
                {"name": "view_item", "params": {"item_id": "SKU-1"}},
                {"name": "add_to_cart", "params": {"item_id": "SKU-1", "value": 9.99}},
            ],
        },
        credentials={"ga4_measurement": _CRED_ID},
    )
    await Ga4Node().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["user_id"] == "u_42"
    assert len(body["events"]) == 2
    assert body["events"][0]["name"] == "view_item"
    assert body["events"][1]["params"]["value"] == 9.99


def test_track_events_rejects_empty_list() -> None:
    with pytest.raises(ValueError, match="'events' must be a non-empty list"):
        build_request("track_events", {"client_id": _CLIENT_ID, "events": []})


def test_track_events_rejects_event_without_name() -> None:
    with pytest.raises(ValueError, match="non-empty 'name'"):
        build_request(
            "track_events",
            {"client_id": _CLIENT_ID, "events": [{"params": {}}]},
        )


# --- validate_event ------------------------------------------------


@respx.mock
async def test_validate_event_routes_to_debug_endpoint() -> None:
    route = respx.post(f"{_API}/debug/mp/collect").mock(
        return_value=Response(
            200, json={"validationMessages": []},
        ),
    )
    node = Node(
        id="node_1",
        name="GA4",
        type="weftlyflow.ga4",
        parameters={
            "operation": "validate_event",
            "client_id": _CLIENT_ID,
            "event_name": "sign_up",
        },
        credentials={"ga4_measurement": _CRED_ID},
    )
    await Ga4Node().execute(_ctx_for(node), [Item()])
    assert route.called


# --- user_properties -----------------------------------------------


@respx.mock
async def test_user_properties_wraps_values_in_value_dict() -> None:
    route = respx.post(f"{_API}/mp/collect").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="GA4",
        type="weftlyflow.ga4",
        parameters={
            "operation": "user_properties",
            "client_id": _CLIENT_ID,
            "user_properties": {"plan": "pro", "signup_source": "referral"},
        },
        credentials={"ga4_measurement": _CRED_ID},
    )
    await Ga4Node().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["user_properties"] == {
        "plan": {"value": "pro"},
        "signup_source": {"value": "referral"},
    }
    assert body["events"] == [{"name": "session_start", "params": {}}]


def test_user_properties_requires_dict() -> None:
    with pytest.raises(ValueError, match="'user_properties' dict is required"):
        build_request("user_properties", {"client_id": _CLIENT_ID})


# --- optional envelope fields --------------------------------------


@respx.mock
async def test_timestamp_and_non_personalized_forwarded() -> None:
    route = respx.post(f"{_API}/mp/collect").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="GA4",
        type="weftlyflow.ga4",
        parameters={
            "operation": "track_event",
            "client_id": _CLIENT_ID,
            "event_name": "purchase",
            "timestamp_micros": 1_714_000_000_000_000,
            "non_personalized_ads": True,
        },
        credentials={"ga4_measurement": _CRED_ID},
    )
    await Ga4Node().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["timestamp_micros"] == 1_714_000_000_000_000
    assert body["non_personalized_ads"] is True


# --- errors --------------------------------------------------------


@respx.mock
async def test_api_error_is_parsed() -> None:
    respx.post(f"{_API}/mp/collect").mock(
        return_value=Response(400, json={"error": "measurement_id not found"}),
    )
    node = Node(
        id="node_1",
        name="GA4",
        type="weftlyflow.ga4",
        parameters={
            "operation": "track_event",
            "client_id": _CLIENT_ID,
            "event_name": "sign_up",
        },
        credentials={"ga4_measurement": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="measurement_id not found"):
        await Ga4Node().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="GA4",
        type="weftlyflow.ga4",
        parameters={
            "operation": "track_event",
            "client_id": _CLIENT_ID,
            "event_name": "sign_up",
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await Ga4Node().execute(_ctx_for(node), [Item()])


async def test_empty_api_secret_raises() -> None:
    resolver = _resolver(api_secret="")
    node = Node(
        id="node_1",
        name="GA4",
        type="weftlyflow.ga4",
        parameters={
            "operation": "track_event",
            "client_id": _CLIENT_ID,
            "event_name": "sign_up",
        },
        credentials={"ga4_measurement": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_secret'"):
        await Ga4Node().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
