"""Unit tests for :class:`ZoomNode`.

Exercises every supported operation against a respx-mocked Zoom v2 API.
Verifies the Server-to-Server Bearer auth, the user-keyed listing path
(``/users/{userId}/meetings``), the ``me`` shorthand, the PATCH verb on
updates, the ``occurrence_id`` query on single-occurrence deletes, the
``/past_meetings/{id}/participants`` analytics path, the
``list_type``/``type`` enum validation, page-size capping at 300, and
the ``{message, code}`` error envelope.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import ZoomApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.zoom import ZoomNode
from weftlyflow.nodes.integrations.zoom.operations import build_request

_CRED_ID: str = "cr_zoom"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "zoom-token"
_ACCOUNT: str = "acct-123"
_BASE: str = "https://api.zoom.us/v2"


def _resolver() -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.zoom_api": ZoomApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.zoom_api",
                {"access_token": _TOKEN, "account_id": _ACCOUNT},
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


# --- list_meetings ---------------------------------------------------


@respx.mock
async def test_list_meetings_uses_me_shorthand_and_bearer() -> None:
    route = respx.get(f"{_BASE}/users/me/meetings").mock(
        return_value=Response(200, json={"meetings": []}),
    )
    node = Node(
        id="node_1",
        name="Zoom",
        type="weftlyflow.zoom",
        parameters={
            "operation": "list_meetings",
            "list_type": "scheduled",
            "page_size": 25,
        },
        credentials={"zoom_api": _CRED_ID},
    )
    await ZoomNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert request.url.params.get("type") == "scheduled"
    assert request.url.params.get("page_size") == "25"


@respx.mock
async def test_list_meetings_targets_specific_user() -> None:
    route = respx.get(f"{_BASE}/users/alice@acme.io/meetings").mock(
        return_value=Response(200, json={"meetings": []}),
    )
    node = Node(
        id="node_1",
        name="Zoom",
        type="weftlyflow.zoom",
        parameters={
            "operation": "list_meetings",
            "user_id": "alice@acme.io",
        },
        credentials={"zoom_api": _CRED_ID},
    )
    await ZoomNode().execute(_ctx_for(node), [Item()])
    assert route.called


def test_list_meetings_rejects_invalid_list_type() -> None:
    with pytest.raises(ValueError, match="'list_type' must be one of"):
        build_request("list_meetings", {"list_type": "garbage"})


def test_page_size_caps_at_max() -> None:
    _, _, _, query = build_request("list_meetings", {"page_size": 10_000})
    assert query["page_size"] == 300


def test_page_size_rejects_non_integer() -> None:
    with pytest.raises(ValueError, match="'page_size' must be a positive integer"):
        build_request("list_meetings", {"page_size": "many"})


# --- get_meeting -----------------------------------------------------


@respx.mock
async def test_get_meeting_hits_numeric_id() -> None:
    route = respx.get(f"{_BASE}/meetings/98765").mock(
        return_value=Response(200, json={"id": 98765}),
    )
    node = Node(
        id="node_1",
        name="Zoom",
        type="weftlyflow.zoom",
        parameters={"operation": "get_meeting", "meeting_id": "98765"},
        credentials={"zoom_api": _CRED_ID},
    )
    await ZoomNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- create_meeting --------------------------------------------------


@respx.mock
async def test_create_meeting_posts_topic_and_type() -> None:
    route = respx.post(f"{_BASE}/users/me/meetings").mock(
        return_value=Response(201, json={"id": 1, "topic": "Sync"}),
    )
    node = Node(
        id="node_1",
        name="Zoom",
        type="weftlyflow.zoom",
        parameters={
            "operation": "create_meeting",
            "topic": "Sync",
            "type": 2,
            "start_time": "2026-05-01T10:00:00Z",
            "duration": 30,
        },
        credentials={"zoom_api": _CRED_ID},
    )
    await ZoomNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["topic"] == "Sync"
    assert body["type"] == 2
    assert body["start_time"] == "2026-05-01T10:00:00Z"
    assert body["duration"] == 30


def test_create_meeting_requires_topic() -> None:
    with pytest.raises(ValueError, match="'topic' is required"):
        build_request("create_meeting", {})


def test_create_meeting_rejects_invalid_type() -> None:
    with pytest.raises(ValueError, match="'type' must be one of"):
        build_request("create_meeting", {"topic": "x", "type": 99})


# --- update_meeting (PATCH) ------------------------------------------


@respx.mock
async def test_update_meeting_uses_patch_verb() -> None:
    route = respx.patch(f"{_BASE}/meetings/123").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="Zoom",
        type="weftlyflow.zoom",
        parameters={
            "operation": "update_meeting",
            "meeting_id": "123",
            "document": {"topic": "Renamed"},
        },
        credentials={"zoom_api": _CRED_ID},
    )
    await ZoomNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.method == "PATCH"


def test_update_meeting_rejects_empty_patch() -> None:
    with pytest.raises(ValueError, match="non-empty JSON object"):
        build_request(
            "update_meeting", {"meeting_id": "1", "document": {}},
        )


# --- delete_meeting --------------------------------------------------


@respx.mock
async def test_delete_meeting_passes_occurrence_id_as_query() -> None:
    route = respx.delete(f"{_BASE}/meetings/555").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="Zoom",
        type="weftlyflow.zoom",
        parameters={
            "operation": "delete_meeting",
            "meeting_id": "555",
            "occurrence_id": "occ-9",
        },
        credentials={"zoom_api": _CRED_ID},
    )
    await ZoomNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.url.params.get("occurrence_id") == "occ-9"


# --- list_past_participants ------------------------------------------


@respx.mock
async def test_list_past_participants_hits_analytics_path() -> None:
    route = respx.get(f"{_BASE}/past_meetings/321/participants").mock(
        return_value=Response(200, json={"participants": []}),
    )
    node = Node(
        id="node_1",
        name="Zoom",
        type="weftlyflow.zoom",
        parameters={
            "operation": "list_past_participants",
            "meeting_id": "321",
            "next_page_token": "cursor-x",
        },
        credentials={"zoom_api": _CRED_ID},
    )
    await ZoomNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.url.params.get("next_page_token") == "cursor-x"


# --- errors ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_code_and_message() -> None:
    respx.get(f"{_BASE}/meetings/404").mock(
        return_value=Response(
            404,
            json={"code": 3001, "message": "Meeting does not exist"},
        ),
    )
    node = Node(
        id="node_1",
        name="Zoom",
        type="weftlyflow.zoom",
        parameters={"operation": "get_meeting", "meeting_id": "404"},
        credentials={"zoom_api": _CRED_ID},
    )
    with pytest.raises(
        NodeExecutionError, match="code 3001: Meeting does not exist",
    ):
        await ZoomNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Zoom",
        type="weftlyflow.zoom",
        parameters={"operation": "list_meetings"},
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
        await ZoomNode().execute(ctx, [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("purge_account", {})


def test_meeting_id_required_for_get() -> None:
    with pytest.raises(ValueError, match="'meeting_id' is required"):
        build_request("get_meeting", {})
