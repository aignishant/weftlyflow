"""Unit tests for :class:`MixpanelNode` and ``MixpanelApiCredential``.

Exercises Mixpanel's distinctive transport split:

* **Ingestion** (``track_event``/``engage_user``/``update_group``) folds
  the payload into ``?data=<base64(JSON)>`` on a bodyless POST; success
  is signaled by the text ``"1"``.
* **``import_events``** POSTs a JSON array to ``/import`` under HTTP
  Basic auth with the ``api_secret`` as the username and an empty
  password.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import MixpanelApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.mixpanel import MixpanelNode
from weftlyflow.nodes.integrations.mixpanel.operations import build_request

_CRED_ID: str = "cr_mixpanel"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "tok_abc123"
_SECRET: str = "sec_xyz789"
_API: str = "https://api.mixpanel.com"


def _resolver(
    *, token: str = _TOKEN, secret: str | None = _SECRET,
) -> InMemoryCredentialResolver:
    payload: dict[str, str] = {"project_token": token}
    if secret is not None:
        payload["api_secret"] = secret
    return InMemoryCredentialResolver(
        types={"weftlyflow.mixpanel_api": MixpanelApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.mixpanel_api",
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


def _decode_data(request: httpx.Request) -> dict:
    encoded = request.url.params["data"]
    return json.loads(base64.b64decode(encoded).decode("utf-8"))


# --- credential: inject is a no-op; auth rides inside body ---------


async def test_credential_inject_is_no_op() -> None:
    request = httpx.Request("POST", f"{_API}/track")
    out = await MixpanelApiCredential().inject({"project_token": _TOKEN}, request)
    assert "Authorization" not in out.headers
    assert str(out.url) == f"{_API}/track"


# --- track_event ---------------------------------------------------


@respx.mock
async def test_track_event_encodes_body_as_base64_query() -> None:
    route = respx.post(f"{_API}/track").mock(return_value=Response(200, text="1"))
    node = Node(
        id="node_1",
        name="Mixpanel",
        type="weftlyflow.mixpanel",
        parameters={
            "operation": "track_event",
            "distinct_id": "u_1",
            "event": "Signed Up",
            "properties": {"plan": "pro"},
        },
        credentials={"mixpanel_api": _CRED_ID},
    )
    await MixpanelNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    # Body MUST be empty — payload rides in the query string.
    assert sent.content == b""
    decoded = _decode_data(sent)
    assert decoded == {
        "event": "Signed Up",
        "properties": {
            "plan": "pro",
            "token": _TOKEN,
            "distinct_id": "u_1",
        },
    }


def test_track_event_requires_event() -> None:
    with pytest.raises(ValueError, match="'event' is required"):
        build_request(
            "track_event", {"distinct_id": "u"}, project_token=_TOKEN,
        )


def test_track_event_requires_distinct_id() -> None:
    with pytest.raises(ValueError, match="'distinct_id' is required"):
        build_request(
            "track_event", {"event": "E"}, project_token=_TOKEN,
        )


# --- engage_user ---------------------------------------------------


@respx.mock
async def test_engage_user_uses_dollar_envelope() -> None:
    route = respx.post(f"{_API}/engage").mock(return_value=Response(200, text="1"))
    node = Node(
        id="node_1",
        name="Mixpanel",
        type="weftlyflow.mixpanel",
        parameters={
            "operation": "engage_user",
            "distinct_id": "u_1",
            "set_verb": "$set",
            "properties": {"email": "a@b.c"},
        },
        credentials={"mixpanel_api": _CRED_ID},
    )
    await MixpanelNode().execute(_ctx_for(node), [Item()])
    decoded = _decode_data(route.calls.last.request)
    assert decoded == {
        "$token": _TOKEN,
        "$distinct_id": "u_1",
        "$set": {"email": "a@b.c"},
    }


@respx.mock
async def test_engage_user_honours_set_once_verb() -> None:
    route = respx.post(f"{_API}/engage").mock(return_value=Response(200, text="1"))
    node = Node(
        id="node_1",
        name="Mixpanel",
        type="weftlyflow.mixpanel",
        parameters={
            "operation": "engage_user",
            "distinct_id": "u_1",
            "set_verb": "$set_once",
            "properties": {"first_seen": "2026-04-23"},
        },
        credentials={"mixpanel_api": _CRED_ID},
    )
    await MixpanelNode().execute(_ctx_for(node), [Item()])
    decoded = _decode_data(route.calls.last.request)
    assert "$set_once" in decoded
    assert "$set" not in decoded


def test_engage_user_requires_properties() -> None:
    with pytest.raises(ValueError, match="'properties' is required"):
        build_request(
            "engage_user", {"distinct_id": "u"}, project_token=_TOKEN,
        )


# --- update_group --------------------------------------------------


@respx.mock
async def test_update_group_uses_group_key_envelope() -> None:
    route = respx.post(f"{_API}/groups").mock(return_value=Response(200, text="1"))
    node = Node(
        id="node_1",
        name="Mixpanel",
        type="weftlyflow.mixpanel",
        parameters={
            "operation": "update_group",
            "group_key": "company",
            "group_id": "acme",
            "properties": {"plan": "enterprise"},
        },
        credentials={"mixpanel_api": _CRED_ID},
    )
    await MixpanelNode().execute(_ctx_for(node), [Item()])
    decoded = _decode_data(route.calls.last.request)
    assert decoded == {
        "$token": _TOKEN,
        "$group_key": "company",
        "$group_id": "acme",
        "$set": {"plan": "enterprise"},
    }


def test_update_group_requires_group_id() -> None:
    with pytest.raises(ValueError, match="'group_id' is required"):
        build_request(
            "update_group",
            {"group_key": "company", "properties": {"x": 1}},
            project_token=_TOKEN,
        )


# --- import_events -------------------------------------------------


@respx.mock
async def test_import_events_uses_basic_auth_with_api_secret() -> None:
    route = respx.post(f"{_API}/import").mock(
        return_value=Response(200, json={"num_records_imported": 2}),
    )
    node = Node(
        id="node_1",
        name="Mixpanel",
        type="weftlyflow.mixpanel",
        parameters={
            "operation": "import_events",
            "project_id": "12345",
            "events": [
                {"event": "A", "properties": {"distinct_id": "u1"}},
                {"event": "B", "properties": {"distinct_id": "u2"}},
            ],
        },
        credentials={"mixpanel_api": _CRED_ID},
    )
    await MixpanelNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    expected = "Basic " + base64.b64encode(f"{_SECRET}:".encode()).decode("ascii")
    assert sent.headers["Authorization"] == expected
    # /import takes a real JSON array body (no ?data= query).
    assert "data" not in sent.url.params
    assert sent.url.params["projectId"] == "12345"
    body = json.loads(sent.content)
    assert isinstance(body, list)
    assert body[0]["properties"]["token"] == _TOKEN
    assert body[1]["properties"]["distinct_id"] == "u2"


async def test_import_events_without_api_secret_raises() -> None:
    resolver = _resolver(secret=None)
    node = Node(
        id="node_1",
        name="Mixpanel",
        type="weftlyflow.mixpanel",
        parameters={
            "operation": "import_events",
            "events": [{"event": "A", "properties": {"distinct_id": "u1"}}],
        },
        credentials={"mixpanel_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'api_secret' is required"):
        await MixpanelNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_import_events_rejects_empty_list() -> None:
    with pytest.raises(ValueError, match="non-empty list"):
        build_request(
            "import_events", {"events": []}, project_token=_TOKEN,
        )


def test_import_events_rejects_non_dict_entry() -> None:
    with pytest.raises(ValueError, match="each 'events' entry must be a dict"):
        build_request(
            "import_events",
            {"events": ["not-a-dict"]},
            project_token=_TOKEN,
        )


# --- errors --------------------------------------------------------


@respx.mock
async def test_ingestion_zero_response_is_treated_as_failure() -> None:
    respx.post(f"{_API}/track").mock(return_value=Response(200, text="0"))
    node = Node(
        id="node_1",
        name="Mixpanel",
        type="weftlyflow.mixpanel",
        parameters={
            "operation": "track_event",
            "distinct_id": "u",
            "event": "E",
        },
        credentials={"mixpanel_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="mixpanel returned '0'"):
        await MixpanelNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_import_http_error_is_raised() -> None:
    respx.post(f"{_API}/import").mock(
        return_value=Response(401, json={"error": "unauthorized"}),
    )
    node = Node(
        id="node_1",
        name="Mixpanel",
        type="weftlyflow.mixpanel",
        parameters={
            "operation": "import_events",
            "events": [{"event": "A", "properties": {"distinct_id": "u"}}],
        },
        credentials={"mixpanel_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="unauthorized"):
        await MixpanelNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Mixpanel",
        type="weftlyflow.mixpanel",
        parameters={
            "operation": "track_event",
            "distinct_id": "u",
            "event": "E",
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await MixpanelNode().execute(_ctx_for(node), [Item()])


async def test_empty_project_token_raises() -> None:
    resolver = _resolver(token="")
    node = Node(
        id="node_1",
        name="Mixpanel",
        type="weftlyflow.mixpanel",
        parameters={
            "operation": "track_event",
            "distinct_id": "u",
            "event": "E",
        },
        credentials={"mixpanel_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'project_token'"):
        await MixpanelNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {}, project_token=_TOKEN)
