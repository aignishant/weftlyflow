"""Unit tests for :class:`MapboxNode` and ``MapboxApiCredential``.

Exercises the distinctive query-param ``?access_token=`` auth (no
``Authorization`` header), the geocoding URL shape that puts the query
in the path, and the directions/isochrone routing profile + coordinate
semicolon-join conventions.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import MapboxApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.mapbox import MapboxNode
from weftlyflow.nodes.integrations.mapbox.operations import build_request

_CRED_ID: str = "cr_mapbox"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "pk.test-token"
_BASE: str = "https://api.mapbox.com"


def _resolver(*, access_token: str = _TOKEN) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.mapbox_api": MapboxApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.mapbox_api",
                {"access_token": access_token},
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


# --- credential.inject ----------------------------------------------


async def test_credential_inject_appends_access_token_query_param() -> None:
    request = httpx.Request("GET", f"{_BASE}/geocoding/v5/mapbox.places/Paris.json")
    out = await MapboxApiCredential().inject({"access_token": _TOKEN}, request)
    assert out.url.params["access_token"] == _TOKEN
    assert "Authorization" not in out.headers


async def test_credential_inject_preserves_existing_query_params() -> None:
    request = httpx.Request(
        "GET",
        f"{_BASE}/geocoding/v5/mapbox.places/Paris.json?limit=3",
    )
    out = await MapboxApiCredential().inject({"access_token": _TOKEN}, request)
    assert out.url.params["limit"] == "3"
    assert out.url.params["access_token"] == _TOKEN


# --- forward geocode -------------------------------------------------


@respx.mock
async def test_forward_geocode_percent_encodes_search_in_path() -> None:
    route = respx.get(f"{_BASE}/geocoding/v5/mapbox.places/New%20York.json").mock(
        return_value=Response(200, json={"features": []}),
    )
    node = Node(
        id="node_1",
        name="Mapbox",
        type="weftlyflow.mapbox",
        parameters={
            "operation": "forward_geocode",
            "search_text": "New York",
            "limit": 3,
            "country": "us",
        },
        credentials={"mapbox_api": _CRED_ID},
    )
    await MapboxNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params["access_token"] == _TOKEN
    assert params["limit"] == "3"
    assert params["country"] == "us"


def test_forward_geocode_requires_search_text() -> None:
    with pytest.raises(ValueError, match="'search_text' is required"):
        build_request("forward_geocode", {})


# --- reverse geocode -------------------------------------------------


@respx.mock
async def test_reverse_geocode_joins_coordinates_in_path() -> None:
    route = respx.get(
        f"{_BASE}/geocoding/v5/mapbox.places/-73.99,40.73.json",
    ).mock(return_value=Response(200, json={"features": []}))
    node = Node(
        id="node_1",
        name="Mapbox",
        type="weftlyflow.mapbox",
        parameters={
            "operation": "reverse_geocode",
            "longitude": "-73.99",
            "latitude": "40.73",
            "limit": 1,
        },
        credentials={"mapbox_api": _CRED_ID},
    )
    await MapboxNode().execute(_ctx_for(node), [Item()])
    assert route.called


def test_reverse_geocode_requires_both_coordinates() -> None:
    with pytest.raises(ValueError, match="'longitude' is required"):
        build_request("reverse_geocode", {})
    with pytest.raises(ValueError, match="'latitude' is required"):
        build_request("reverse_geocode", {"longitude": "-73.99"})


# --- directions ------------------------------------------------------


@respx.mock
async def test_directions_uses_profile_and_coordinates_in_path() -> None:
    route = respx.get(
        f"{_BASE}/directions/v5/mapbox/driving/-73.99,40.73;-73.98,40.72",
    ).mock(return_value=Response(200, json={"routes": []}))
    node = Node(
        id="node_1",
        name="Mapbox",
        type="weftlyflow.mapbox",
        parameters={
            "operation": "directions",
            "coordinates": "-73.99,40.73;-73.98,40.72",
            "geometries": "geojson",
            "steps": True,
        },
        credentials={"mapbox_api": _CRED_ID},
    )
    await MapboxNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params["geometries"] == "geojson"
    assert params["steps"] == "true"


def test_directions_requires_coordinates() -> None:
    with pytest.raises(ValueError, match="'coordinates' is required"):
        build_request("directions", {})


# --- matrix ----------------------------------------------------------


@respx.mock
async def test_matrix_uses_matrix_v1_prefix() -> None:
    route = respx.get(
        f"{_BASE}/directions-matrix/v1/mapbox/driving/0,0;1,1",
    ).mock(return_value=Response(200, json={"durations": []}))
    node = Node(
        id="node_1",
        name="Mapbox",
        type="weftlyflow.mapbox",
        parameters={
            "operation": "matrix",
            "coordinates": "0,0;1,1",
            "annotations": "duration",
        },
        credentials={"mapbox_api": _CRED_ID},
    )
    await MapboxNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- isochrone -------------------------------------------------------


@respx.mock
async def test_isochrone_accepts_contours_minutes() -> None:
    route = respx.get(
        f"{_BASE}/isochrone/v1/mapbox/driving/-73.99,40.73",
    ).mock(return_value=Response(200, json={"features": []}))
    node = Node(
        id="node_1",
        name="Mapbox",
        type="weftlyflow.mapbox",
        parameters={
            "operation": "isochrone",
            "coordinates": "-73.99,40.73",
            "contours_minutes": "5,10,15",
            "polygons": True,
        },
        credentials={"mapbox_api": _CRED_ID},
    )
    await MapboxNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params["contours_minutes"] == "5,10,15"
    assert params["polygons"] == "true"


def test_isochrone_requires_a_contour() -> None:
    with pytest.raises(ValueError, match="one of 'contours_minutes' or 'contours_meters'"):
        build_request(
            "isochrone",
            {"coordinates": "0,0"},
        )


# --- errors ----------------------------------------------------------


@respx.mock
async def test_error_envelope_is_parsed() -> None:
    respx.get(f"{_BASE}/geocoding/v5/mapbox.places/X.json").mock(
        return_value=Response(401, json={"message": "Not Authorized - No Token"}),
    )
    node = Node(
        id="node_1",
        name="Mapbox",
        type="weftlyflow.mapbox",
        parameters={"operation": "forward_geocode", "search_text": "X"},
        credentials={"mapbox_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Not Authorized"):
        await MapboxNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Mapbox",
        type="weftlyflow.mapbox",
        parameters={"operation": "forward_geocode", "search_text": "X"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await MapboxNode().execute(_ctx_for(node), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
