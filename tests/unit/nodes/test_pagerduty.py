"""Unit tests for :class:`PagerDutyNode`.

Exercises every supported operation against a respx-mocked PagerDuty
REST v2 API. Verifies the distinctive ``Authorization: Token token=<key>``
header, the ``From`` header required on mutating calls, the
single-root-key envelope (``incident`` / ``note``), and the
``statuses[]``-style repeated-query-key filters on listings.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import PagerDutyApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.pagerduty import PagerDutyNode
from weftlyflow.nodes.integrations.pagerduty.operations import build_request

_CRED_ID: str = "cr_pd"
_PROJECT_ID: str = "pr_test"
_BASE: str = "https://api.pagerduty.com"


def _resolver(
    *,
    api_key: str = "u+abcdef123",
    from_email: str = "oncall@acme.io",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.pagerduty_api": PagerDutyApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.pagerduty_api",
                {"api_key": api_key, "from_email": from_email},
                _PROJECT_ID,
            ),
        },
    )


def _ctx_for(
    node: Node,
    *,
    inputs: list[Item] | None = None,
    resolver: InMemoryCredentialResolver | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [], project_id=_PROJECT_ID)
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": list(inputs or [])},
        credential_resolver=resolver,
    )


# --- list_incidents -----------------------------------------------------


@respx.mock
async def test_list_incidents_uses_token_prefix_header_and_repeated_keys() -> None:
    route = respx.get(f"{_BASE}/incidents").mock(
        return_value=Response(200, json={"incidents": [{"id": "P1"}]}),
    )
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={
            "operation": "list_incidents",
            "statuses": "triggered, acknowledged",
            "urgencies": "high",
            "limit": 5,
        },
        credentials={"pagerduty_api": _CRED_ID},
    )
    out = await PagerDutyNode().execute(
        _ctx_for(node, resolver=_resolver()), [Item()],
    )
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Token token=u+abcdef123"
    assert request.headers["Accept"] == "application/vnd.pagerduty+json;version=2"
    query = str(request.url)
    assert "statuses%5B%5D=triggered" in query
    assert "statuses%5B%5D=acknowledged" in query
    assert "urgencies%5B%5D=high" in query
    assert "limit=5" in query
    [result] = out[0]
    assert result.json["incidents"] == [{"id": "P1"}]


async def test_list_incidents_rejects_invalid_status() -> None:
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={"operation": "list_incidents", "statuses": "bogus"},
        credentials={"pagerduty_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid status"):
        await PagerDutyNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- get_incident -------------------------------------------------------


@respx.mock
async def test_get_incident_escapes_id_in_path() -> None:
    route = respx.get(f"{_BASE}/incidents/PX%2F42").mock(
        return_value=Response(200, json={"incident": {"id": "PX/42"}}),
    )
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={"operation": "get_incident", "incident_id": "PX/42"},
        credentials={"pagerduty_api": _CRED_ID},
    )
    await PagerDutyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- create_incident ----------------------------------------------------


@respx.mock
async def test_create_incident_sends_envelope_and_from_header() -> None:
    route = respx.post(f"{_BASE}/incidents").mock(
        return_value=Response(201, json={"incident": {"id": "P9"}}),
    )
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={
            "operation": "create_incident",
            "title": "Latency spike",
            "service_id": "PSERVICE",
            "urgency": "high",
            "body": "p99 breached",
        },
        credentials={"pagerduty_api": _CRED_ID},
    )
    await PagerDutyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    assert request.headers["From"] == "oncall@acme.io"
    body = json.loads(request.content)
    assert body == {
        "incident": {
            "type": "incident",
            "title": "Latency spike",
            "service": {"id": "PSERVICE", "type": "service_reference"},
            "urgency": "high",
            "body": {"type": "incident_body", "details": "p99 breached"},
        },
    }


@respx.mock
async def test_create_incident_prefers_per_call_from_email_override() -> None:
    route = respx.post(f"{_BASE}/incidents").mock(
        return_value=Response(201, json={"incident": {"id": "P9"}}),
    )
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={
            "operation": "create_incident",
            "title": "x",
            "service_id": "PS",
            "from_email": "override@acme.io",
        },
        credentials={"pagerduty_api": _CRED_ID},
    )
    await PagerDutyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.calls.last.request.headers["From"] == "override@acme.io"


async def test_create_incident_requires_from_email() -> None:
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={
            "operation": "create_incident",
            "title": "x",
            "service_id": "PS",
        },
        credentials={"pagerduty_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="from_email"):
        await PagerDutyNode().execute(
            _ctx_for(node, resolver=_resolver(from_email="")), [Item()],
        )


# --- update_incident ----------------------------------------------------


@respx.mock
async def test_update_incident_wraps_fields_in_envelope() -> None:
    route = respx.put(f"{_BASE}/incidents/P1").mock(
        return_value=Response(200, json={"incident": {"id": "P1"}}),
    )
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={
            "operation": "update_incident",
            "incident_id": "P1",
            "fields": {"status": "resolved", "resolution": "fixed"},
        },
        credentials={"pagerduty_api": _CRED_ID},
    )
    await PagerDutyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "incident": {
            "type": "incident_reference",
            "status": "resolved",
            "resolution": "fixed",
        },
    }


async def test_update_incident_rejects_unknown_field() -> None:
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={
            "operation": "update_incident",
            "incident_id": "P1",
            "fields": {"foo": "bar"},
        },
        credentials={"pagerduty_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="unknown incident field"):
        await PagerDutyNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- add_note -----------------------------------------------------------


@respx.mock
async def test_add_note_posts_to_notes_endpoint() -> None:
    route = respx.post(f"{_BASE}/incidents/P1/notes").mock(
        return_value=Response(201, json={"note": {"id": "N1"}}),
    )
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={
            "operation": "add_note",
            "incident_id": "P1",
            "content": "rolled back deploy",
        },
        credentials={"pagerduty_api": _CRED_ID},
    )
    await PagerDutyNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"note": {"content": "rolled back deploy"}}


# --- errors / credentials -----------------------------------------------


@respx.mock
async def test_api_error_surfaces_message_and_errors_list() -> None:
    respx.get(f"{_BASE}/incidents").mock(
        return_value=Response(
            400,
            json={
                "error": {
                    "message": "Invalid Input Provided",
                    "errors": ["status is invalid"],
                },
            },
        ),
    )
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={"operation": "list_incidents"},
        credentials={"pagerduty_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="status is invalid"):
        await PagerDutyNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={"operation": "list_incidents"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await PagerDutyNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_empty_api_key_raises() -> None:
    node = Node(
        id="node_1",
        name="PagerDuty",
        type="weftlyflow.pagerduty",
        parameters={"operation": "list_incidents"},
        credentials={"pagerduty_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'api_key'"):
        await PagerDutyNode().execute(
            _ctx_for(node, resolver=_resolver(api_key="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_list_caps_limit_at_max() -> None:
    _, _, _, query = build_request("list_incidents", {"limit": 5_000})
    assert query["limit"] == 100


def test_build_request_update_requires_fields() -> None:
    with pytest.raises(ValueError, match="'fields'"):
        build_request("update_incident", {"incident_id": "P1"})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("delete_incident", {})
