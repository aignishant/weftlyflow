"""Unit tests for :class:`MicrosoftGraphNode`.

Exercises every supported operation against a respx-mocked
``graph.microsoft.com/v1.0`` endpoint. Verifies the Bearer auth, the
conditional ``ConsistencyLevel: eventual`` header emitted *only* on
advanced-query list calls (``$search``, ``$count``, ``endswith``,
``ne``, ``not``, ``startswith``), the ``me`` vs
``/users/{id}`` mailbox/calendar path split, and the
``{error: {code, message}}`` nested error envelope.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import MicrosoftGraphCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.microsoft_graph import MicrosoftGraphNode
from weftlyflow.nodes.integrations.microsoft_graph.operations import build_request

_CRED_ID: str = "cr_graph"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "graph-token"
_TENANT: str = "tenant-abc"
_BASE: str = "https://graph.microsoft.com/v1.0"


def _resolver() -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.microsoft_graph": MicrosoftGraphCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.microsoft_graph",
                {"access_token": _TOKEN, "tenant_id": _TENANT},
                _PROJECT_ID,
            ),
        },
    )


def _ctx_for(node: Node) -> ExecutionContext:
    wf = build_workflow([node], [], project_id=_PROJECT_ID)
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": []},
        credential_resolver=_resolver(),
    )


# --- list_users ------------------------------------------------------


@respx.mock
async def test_list_users_plain_does_not_emit_consistency_header() -> None:
    route = respx.get(f"{_BASE}/users").mock(
        return_value=Response(200, json={"value": []}),
    )
    node = Node(
        id="node_1",
        name="Graph",
        type="weftlyflow.microsoft_graph",
        parameters={
            "operation": "list_users",
            "select": "id,displayName",
            "top": 10,
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    await MicrosoftGraphNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert "ConsistencyLevel" not in request.headers
    assert request.url.params.get("$select") == "id,displayName"
    assert request.url.params.get("$top") == "10"


@respx.mock
async def test_list_users_with_search_emits_consistency_header() -> None:
    route = respx.get(f"{_BASE}/users").mock(
        return_value=Response(200, json={"value": []}),
    )
    node = Node(
        id="node_1",
        name="Graph",
        type="weftlyflow.microsoft_graph",
        parameters={
            "operation": "list_users",
            "search": '"displayName:ada"',
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    await MicrosoftGraphNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["ConsistencyLevel"] == "eventual"
    assert request.url.params.get("$search") == '"displayName:ada"'


@respx.mock
async def test_list_users_with_count_emits_consistency_header() -> None:
    route = respx.get(f"{_BASE}/users").mock(
        return_value=Response(200, json={"value": [], "@odata.count": 0}),
    )
    node = Node(
        id="node_1",
        name="Graph",
        type="weftlyflow.microsoft_graph",
        parameters={"operation": "list_users", "count": True},
        credentials={"microsoft_graph": _CRED_ID},
    )
    await MicrosoftGraphNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["ConsistencyLevel"] == "eventual"
    assert request.url.params.get("$count") == "true"


@pytest.mark.parametrize(
    "filter_expr",
    [
        "endswith(mail,'@acme.io')",
        "displayName ne 'Ada'",
        "not(accountEnabled eq true)",
        "startswith(displayName,'A')",
    ],
)
def test_advanced_filter_flags_builder(filter_expr: str) -> None:
    _, _, _, _, advanced = build_request(
        "list_users", {"filter": filter_expr},
    )
    assert advanced is True


def test_plain_filter_does_not_trigger_advanced() -> None:
    _, _, _, _, advanced = build_request(
        "list_users", {"filter": "accountEnabled eq true"},
    )
    assert advanced is False


# --- get_user --------------------------------------------------------


@respx.mock
async def test_get_user_targets_users_path() -> None:
    route = respx.get(f"{_BASE}/users/ada@acme.io").mock(
        return_value=Response(200, json={"id": "abc"}),
    )
    node = Node(
        id="node_1",
        name="Graph",
        type="weftlyflow.microsoft_graph",
        parameters={
            "operation": "get_user",
            "user_id": "ada@acme.io",
            "select": "id,mail",
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    await MicrosoftGraphNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.url.params.get("$select") == "id,mail"


def test_get_user_requires_user_id() -> None:
    with pytest.raises(ValueError, match="'user_id' is required"):
        build_request("get_user", {})


# --- list_messages ---------------------------------------------------


@respx.mock
async def test_list_messages_uses_me_shorthand() -> None:
    route = respx.get(f"{_BASE}/me/messages").mock(
        return_value=Response(200, json={"value": []}),
    )
    node = Node(
        id="node_1",
        name="Graph",
        type="weftlyflow.microsoft_graph",
        parameters={
            "operation": "list_messages",
            "order_by": "receivedDateTime desc",
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    await MicrosoftGraphNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.url.params.get("$orderby") == "receivedDateTime desc"


@respx.mock
async def test_list_messages_targets_other_user() -> None:
    route = respx.get(f"{_BASE}/users/bob@acme.io/messages").mock(
        return_value=Response(200, json={"value": []}),
    )
    node = Node(
        id="node_1",
        name="Graph",
        type="weftlyflow.microsoft_graph",
        parameters={
            "operation": "list_messages",
            "user_id": "bob@acme.io",
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    await MicrosoftGraphNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- send_mail -------------------------------------------------------


@respx.mock
async def test_send_mail_posts_wrapped_message() -> None:
    route = respx.post(f"{_BASE}/me/sendMail").mock(return_value=Response(202))
    node = Node(
        id="node_1",
        name="Graph",
        type="weftlyflow.microsoft_graph",
        parameters={
            "operation": "send_mail",
            "message": {
                "subject": "Hi",
                "body": {"contentType": "Text", "content": "Yo"},
                "toRecipients": [
                    {"emailAddress": {"address": "ada@acme.io"}},
                ],
            },
            "save_to_sent_items": True,
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    await MicrosoftGraphNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["message"]["subject"] == "Hi"
    assert body["saveToSentItems"] == "true"


def test_send_mail_requires_non_empty_message() -> None:
    with pytest.raises(ValueError, match="'message' must be a non-empty JSON object"):
        build_request("send_mail", {"message": {}})


# --- list_events / create_event --------------------------------------


@respx.mock
async def test_list_events_targets_me_calendar() -> None:
    route = respx.get(f"{_BASE}/me/events").mock(
        return_value=Response(200, json={"value": []}),
    )
    node = Node(
        id="node_1",
        name="Graph",
        type="weftlyflow.microsoft_graph",
        parameters={"operation": "list_events"},
        credentials={"microsoft_graph": _CRED_ID},
    )
    await MicrosoftGraphNode().execute(_ctx_for(node), [Item()])
    assert route.called


@respx.mock
async def test_create_event_posts_payload() -> None:
    route = respx.post(f"{_BASE}/me/events").mock(
        return_value=Response(201, json={"id": "ev1"}),
    )
    node = Node(
        id="node_1",
        name="Graph",
        type="weftlyflow.microsoft_graph",
        parameters={
            "operation": "create_event",
            "event": {
                "subject": "Design review",
                "start": {"dateTime": "2026-05-01T10:00:00", "timeZone": "UTC"},
                "end": {"dateTime": "2026-05-01T11:00:00", "timeZone": "UTC"},
            },
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    await MicrosoftGraphNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["subject"] == "Design review"


def test_create_event_requires_non_empty_event() -> None:
    with pytest.raises(ValueError, match="'event' must be a non-empty JSON object"):
        build_request("create_event", {"event": {}})


# --- paging + errors -------------------------------------------------


def test_top_caps_at_max() -> None:
    _, _, _, query, _ = build_request("list_users", {"top": 10_000})
    assert query["$top"] == 999


def test_top_rejects_non_integer() -> None:
    with pytest.raises(ValueError, match="'top' must be a positive integer"):
        build_request("list_users", {"top": "many"})


@respx.mock
async def test_api_error_surfaces_nested_code_message() -> None:
    respx.get(f"{_BASE}/users/missing").mock(
        return_value=Response(
            404,
            json={
                "error": {
                    "code": "Request_ResourceNotFound",
                    "message": "Resource 'missing' does not exist",
                },
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Graph",
        type="weftlyflow.microsoft_graph",
        parameters={"operation": "get_user", "user_id": "missing"},
        credentials={"microsoft_graph": _CRED_ID},
    )
    with pytest.raises(
        NodeExecutionError,
        match="Request_ResourceNotFound: Resource 'missing' does not exist",
    ):
        await MicrosoftGraphNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Graph",
        type="weftlyflow.microsoft_graph",
        parameters={"operation": "list_users"},
    )
    wf = build_workflow([node], [], project_id=_PROJECT_ID)
    ctx = ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": []},
        credential_resolver=_resolver(),
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await MicrosoftGraphNode().execute(ctx, [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("purge_tenant", {})
