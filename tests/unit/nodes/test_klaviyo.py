"""Unit tests for :class:`KlaviyoNode` and ``KlaviyoApiCredential``.

Klaviyo uses a non-standard ``Authorization: Klaviyo-API-Key <key>``
scheme and requires a date-versioned ``revision`` header on every
call. Both are set by the credential's :meth:`inject`; the node
just exercises the JSON:API-style ``{"data": {"type": ..., ...}}``
body envelopes.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import KlaviyoApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.klaviyo import KlaviyoNode
from weftlyflow.nodes.integrations.klaviyo.operations import build_request

_CRED_ID: str = "cr_klaviyo"
_PROJECT_ID: str = "pr_test"
_KEY: str = "pk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
_REVISION: str = "2024-10-15"
_API: str = "https://a.klaviyo.com"


def _resolver(
    *, key: str = _KEY, revision: str = _REVISION,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.klaviyo_api": KlaviyoApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.klaviyo_api",
                {"api_key": key, "revision": revision},
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


# --- credential: custom scheme + revision header ------------------


async def test_credential_inject_uses_custom_scheme_and_revision() -> None:
    request = httpx.Request("GET", f"{_API}/api/accounts")
    out = await KlaviyoApiCredential().inject(
        {"api_key": _KEY, "revision": _REVISION}, request,
    )
    assert out.headers["Authorization"] == f"Klaviyo-API-Key {_KEY}"
    assert out.headers["revision"] == _REVISION


async def test_credential_falls_back_to_default_revision_when_blank() -> None:
    request = httpx.Request("GET", f"{_API}/api/accounts")
    out = await KlaviyoApiCredential().inject(
        {"api_key": _KEY, "revision": ""}, request,
    )
    # Default is defined in the credential module; just assert something sane.
    assert out.headers["revision"]
    assert len(out.headers["revision"]) == 10  # YYYY-MM-DD shape


# --- create_event --------------------------------------------------


@respx.mock
async def test_create_event_wraps_payload_in_jsonapi_envelope() -> None:
    route = respx.post(f"{_API}/api/events").mock(
        return_value=Response(202, json={}),
    )
    node = Node(
        id="node_1",
        name="Klaviyo",
        type="weftlyflow.klaviyo",
        parameters={
            "operation": "create_event",
            "metric_name": "Viewed Product",
            "profile": {"email": "a@b.c"},
            "properties": {"sku": "SKU-1"},
            "value": 9.99,
        },
        credentials={"klaviyo_api": _CRED_ID},
    )
    await KlaviyoNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == f"Klaviyo-API-Key {_KEY}"
    assert sent.headers["revision"] == _REVISION
    body = json.loads(sent.content)
    assert body["data"]["type"] == "event"
    attrs = body["data"]["attributes"]
    assert attrs["metric"]["data"]["attributes"]["name"] == "Viewed Product"
    assert attrs["profile"]["data"]["attributes"] == {"email": "a@b.c"}
    assert attrs["properties"] == {"sku": "SKU-1"}
    assert attrs["value"] == 9.99


def test_create_event_requires_profile() -> None:
    with pytest.raises(ValueError, match="'profile' dict is required"):
        build_request("create_event", {"metric_name": "X"})


def test_create_event_requires_metric_name() -> None:
    with pytest.raises(ValueError, match="'metric_name' is required"):
        build_request("create_event", {"profile": {"email": "a@b.c"}})


# --- create_profile ------------------------------------------------


@respx.mock
async def test_create_profile_wraps_attributes_correctly() -> None:
    route = respx.post(f"{_API}/api/profiles").mock(
        return_value=Response(201, json={"data": {"id": "prof_1"}}),
    )
    node = Node(
        id="node_1",
        name="Klaviyo",
        type="weftlyflow.klaviyo",
        parameters={
            "operation": "create_profile",
            "attributes": {"email": "a@b.c", "first_name": "A"},
        },
        credentials={"klaviyo_api": _CRED_ID},
    )
    await KlaviyoNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "data": {
            "type": "profile",
            "attributes": {"email": "a@b.c", "first_name": "A"},
        },
    }


def test_create_profile_requires_attributes() -> None:
    with pytest.raises(ValueError, match="'attributes' dict is required"):
        build_request("create_profile", {})


# --- get_profile ---------------------------------------------------


@respx.mock
async def test_get_profile_uses_id_in_path() -> None:
    route = respx.get(f"{_API}/api/profiles/prof_1").mock(
        return_value=Response(200, json={"data": {"id": "prof_1"}}),
    )
    node = Node(
        id="node_1",
        name="Klaviyo",
        type="weftlyflow.klaviyo",
        parameters={"operation": "get_profile", "profile_id": "prof_1"},
        credentials={"klaviyo_api": _CRED_ID},
    )
    await KlaviyoNode().execute(_ctx_for(node), [Item()])
    assert route.called
    # GET has no body; headers still carry auth.
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == f"Klaviyo-API-Key {_KEY}"


# --- add_profile_to_list -------------------------------------------


@respx.mock
async def test_add_profile_to_list_builds_relationship_references() -> None:
    route = respx.post(
        f"{_API}/api/lists/list_1/relationships/profiles",
    ).mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="Klaviyo",
        type="weftlyflow.klaviyo",
        parameters={
            "operation": "add_profile_to_list",
            "list_id": "list_1",
            "profile_ids": ["p1", "p2"],
        },
        credentials={"klaviyo_api": _CRED_ID},
    )
    await KlaviyoNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "data": [
            {"type": "profile", "id": "p1"},
            {"type": "profile", "id": "p2"},
        ],
    }


def test_add_profile_to_list_rejects_empty_ids() -> None:
    with pytest.raises(ValueError, match="'profile_ids' must be a non-empty list"):
        build_request(
            "add_profile_to_list", {"list_id": "list_1", "profile_ids": []},
        )


# --- errors --------------------------------------------------------


@respx.mock
async def test_api_error_is_parsed_from_jsonapi_errors_array() -> None:
    respx.post(f"{_API}/api/events").mock(
        return_value=Response(
            400,
            json={
                "errors": [
                    {"detail": "email is not valid", "code": "invalid_email"},
                ],
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Klaviyo",
        type="weftlyflow.klaviyo",
        parameters={
            "operation": "create_event",
            "metric_name": "X",
            "profile": {"email": "bad"},
        },
        credentials={"klaviyo_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="email is not valid"):
        await KlaviyoNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Klaviyo",
        type="weftlyflow.klaviyo",
        parameters={
            "operation": "create_event",
            "metric_name": "X",
            "profile": {"email": "a@b.c"},
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await KlaviyoNode().execute(_ctx_for(node), [Item()])


async def test_empty_api_key_raises() -> None:
    resolver = _resolver(key="")
    node = Node(
        id="node_1",
        name="Klaviyo",
        type="weftlyflow.klaviyo",
        parameters={
            "operation": "create_event",
            "metric_name": "X",
            "profile": {"email": "a@b.c"},
        },
        credentials={"klaviyo_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_key'"):
        await KlaviyoNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
