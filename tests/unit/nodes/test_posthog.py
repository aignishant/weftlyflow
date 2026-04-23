"""Unit tests for :class:`PostHogNode` and ``PostHogApiCredential``.

PostHog's ingestion contract is the catalog's only instance of a
credential whose **authentication material lives inside the JSON body**
— every ``/capture``, ``/batch``, and ``/decide`` call carries the
project API key as the top-level ``api_key`` field.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import PostHogApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.posthog import PostHogNode
from weftlyflow.nodes.integrations.posthog.operations import build_request

_CRED_ID: str = "cr_posthog"
_PROJECT_ID: str = "pr_test"
_KEY: str = "phc_project_abc"
_HOST: str = "https://us.i.posthog.com"


def _resolver(
    *, key: str = _KEY, host: str | None = None,
) -> InMemoryCredentialResolver:
    payload: dict[str, str] = {"project_api_key": key}
    if host is not None:
        payload["host"] = host
    return InMemoryCredentialResolver(
        types={"weftlyflow.posthog_api": PostHogApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.posthog_api",
                payload,
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


# --- credential: inject is a no-op; auth rides inside body ---------


async def test_credential_inject_is_no_op() -> None:
    request = httpx.Request("POST", f"{_HOST}/capture/")
    out = await PostHogApiCredential().inject({"project_api_key": _KEY}, request)
    assert "Authorization" not in out.headers
    assert str(out.url) == f"{_HOST}/capture/"


# --- capture -------------------------------------------------------


@respx.mock
async def test_capture_folds_api_key_into_body() -> None:
    route = respx.post(f"{_HOST}/capture/").mock(
        return_value=Response(200, json={"status": 1}),
    )
    node = Node(
        id="node_1",
        name="PostHog",
        type="weftlyflow.posthog",
        parameters={
            "operation": "capture",
            "distinct_id": "u_1",
            "event": "Signed Up",
            "properties": {"plan": "pro"},
        },
        credentials={"posthog_api": _CRED_ID},
    )
    await PostHogNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["api_key"] == _KEY
    assert body["event"] == "Signed Up"
    assert body["distinct_id"] == "u_1"
    assert body["properties"]["plan"] == "pro"


def test_capture_requires_event() -> None:
    with pytest.raises(ValueError, match="'event' is required"):
        build_request("capture", {"distinct_id": "u_1"})


def test_capture_requires_distinct_id() -> None:
    with pytest.raises(ValueError, match="'distinct_id' is required"):
        build_request("capture", {"event": "X"})


# --- batch ---------------------------------------------------------


@respx.mock
async def test_batch_wraps_events_under_batch_key() -> None:
    route = respx.post(f"{_HOST}/batch/").mock(
        return_value=Response(200, json={"status": 1}),
    )
    node = Node(
        id="node_1",
        name="PostHog",
        type="weftlyflow.posthog",
        parameters={
            "operation": "batch",
            "events": [
                {"event": "A", "distinct_id": "u_1"},
                {"event": "B", "distinct_id": "u_2"},
            ],
        },
        credentials={"posthog_api": _CRED_ID},
    )
    await PostHogNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["api_key"] == _KEY
    assert [e["event"] for e in body["batch"]] == ["A", "B"]


def test_batch_rejects_empty_events() -> None:
    with pytest.raises(ValueError, match="non-empty list"):
        build_request("batch", {"events": []})


def test_batch_rejects_non_dict_entries() -> None:
    with pytest.raises(ValueError, match="each 'events' entry must be a dict"):
        build_request("batch", {"events": ["nope"]})


# --- identify ------------------------------------------------------


@respx.mock
async def test_identify_uses_dollar_identify_event() -> None:
    route = respx.post(f"{_HOST}/capture/").mock(
        return_value=Response(200, json={"status": 1}),
    )
    node = Node(
        id="node_1",
        name="PostHog",
        type="weftlyflow.posthog",
        parameters={
            "operation": "identify",
            "distinct_id": "u_1",
            "set": {"email": "a@b.c"},
            "set_once": {"first_seen": "2026-04-23"},
        },
        credentials={"posthog_api": _CRED_ID},
    )
    await PostHogNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["event"] == "$identify"
    assert body["properties"]["$set"] == {"email": "a@b.c"}
    assert body["properties"]["$set_once"] == {"first_seen": "2026-04-23"}


# --- alias ---------------------------------------------------------


@respx.mock
async def test_alias_uses_reserved_create_alias_event() -> None:
    route = respx.post(f"{_HOST}/capture/").mock(
        return_value=Response(200, json={"status": 1}),
    )
    node = Node(
        id="node_1",
        name="PostHog",
        type="weftlyflow.posthog",
        parameters={
            "operation": "alias",
            "distinct_id": "u_new",
            "alias": "u_old",
        },
        credentials={"posthog_api": _CRED_ID},
    )
    await PostHogNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["event"] == "$create_alias"
    assert body["properties"]["alias"] == "u_old"
    assert body["properties"]["distinct_id"] == "u_new"


def test_alias_requires_alias_field() -> None:
    with pytest.raises(ValueError, match="'alias' is required"):
        build_request("alias", {"distinct_id": "u_new"})


# --- decide --------------------------------------------------------


@respx.mock
async def test_decide_posts_to_v3_decide_endpoint() -> None:
    route = respx.post(f"{_HOST}/decide/?v=3").mock(
        return_value=Response(200, json={"featureFlags": {"my-flag": True}}),
    )
    node = Node(
        id="node_1",
        name="PostHog",
        type="weftlyflow.posthog",
        parameters={
            "operation": "decide",
            "distinct_id": "u_1",
            "groups": {"company": "acme"},
            "person_properties": {"plan": "pro"},
        },
        credentials={"posthog_api": _CRED_ID},
    )
    await PostHogNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["api_key"] == _KEY
    assert body["distinct_id"] == "u_1"
    assert body["groups"] == {"company": "acme"}
    assert body["person_properties"] == {"plan": "pro"}


# --- host override -------------------------------------------------


@respx.mock
async def test_credential_host_field_overrides_default() -> None:
    custom = "https://eu.i.posthog.com"
    route = respx.post(f"{custom}/capture/").mock(
        return_value=Response(200, json={"status": 1}),
    )
    node = Node(
        id="node_1",
        name="PostHog",
        type="weftlyflow.posthog",
        parameters={
            "operation": "capture",
            "distinct_id": "u_1",
            "event": "E",
        },
        credentials={"posthog_api": _CRED_ID},
    )
    await PostHogNode().execute(
        _ctx_for(node, resolver=_resolver(host=custom)), [Item()],
    )
    assert route.called


# --- errors --------------------------------------------------------


@respx.mock
async def test_api_error_is_parsed() -> None:
    respx.post(f"{_HOST}/capture/").mock(
        return_value=Response(401, json={"detail": "invalid project key"}),
    )
    node = Node(
        id="node_1",
        name="PostHog",
        type="weftlyflow.posthog",
        parameters={
            "operation": "capture",
            "distinct_id": "u",
            "event": "E",
        },
        credentials={"posthog_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid project key"):
        await PostHogNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="PostHog",
        type="weftlyflow.posthog",
        parameters={
            "operation": "capture",
            "distinct_id": "u",
            "event": "E",
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await PostHogNode().execute(_ctx_for(node), [Item()])


async def test_empty_project_api_key_raises() -> None:
    resolver = _resolver(key="")
    node = Node(
        id="node_1",
        name="PostHog",
        type="weftlyflow.posthog",
        parameters={
            "operation": "capture",
            "distinct_id": "u",
            "event": "E",
        },
        credentials={"posthog_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'project_api_key'"):
        await PostHogNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
