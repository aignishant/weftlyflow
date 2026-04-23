"""Unit tests for :class:`HarvestNode` and ``HarvestApiCredential``.

Harvest is the catalog's first dual-header credential where Bearer
auth and a mandatory ``Harvest-Account-ID`` scoping header are both
required — neither alone is sufficient.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import HarvestApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.harvest import HarvestNode
from weftlyflow.nodes.integrations.harvest.operations import build_request

_CRED_ID: str = "cr_harvest"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "pat_abc"
_ACCOUNT_ID: str = "12345"
_API: str = "https://api.harvestapp.com"


def _resolver(
    *, token: str = _TOKEN, account_id: str = _ACCOUNT_ID,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.harvest_api": HarvestApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.harvest_api",
                {"access_token": token, "account_id": account_id},
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


# --- credential: dual-header auth ---------------------------------


async def test_credential_inject_sets_bearer_and_account_id_headers() -> None:
    request = httpx.Request("GET", f"{_API}/v2/users/me")
    out = await HarvestApiCredential().inject(
        {"access_token": _TOKEN, "account_id": _ACCOUNT_ID}, request,
    )
    assert out.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert out.headers["Harvest-Account-ID"] == _ACCOUNT_ID
    # User-Agent is required by Harvest — credential sets a stable value.
    assert "User-Agent" in out.headers


# --- list_time_entries ---------------------------------------------


@respx.mock
async def test_list_time_entries_passes_filters_as_query() -> None:
    route = respx.get(f"{_API}/v2/time_entries").mock(
        return_value=Response(200, json={"time_entries": []}),
    )
    node = Node(
        id="node_1",
        name="Harvest",
        type="weftlyflow.harvest",
        parameters={
            "operation": "list_time_entries",
            "user_id": "u_1",
            "from": "2026-04-01",
            "to": "2026-04-30",
            "page": 2,
            "per_page": 50,
        },
        credentials={"harvest_api": _CRED_ID},
    )
    await HarvestNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    assert sent.url.params["user_id"] == "u_1"
    assert sent.url.params["from"] == "2026-04-01"
    assert sent.url.params["to"] == "2026-04-30"
    assert sent.url.params["page"] == "2"
    assert sent.url.params["per_page"] == "50"
    assert sent.headers["Harvest-Account-ID"] == _ACCOUNT_ID


# --- create_time_entry ---------------------------------------------


@respx.mock
async def test_create_time_entry_with_hours_duration() -> None:
    route = respx.post(f"{_API}/v2/time_entries").mock(
        return_value=Response(201, json={"id": 1}),
    )
    node = Node(
        id="node_1",
        name="Harvest",
        type="weftlyflow.harvest",
        parameters={
            "operation": "create_time_entry",
            "project_id": 100,
            "task_id": 200,
            "spent_date": "2026-04-23",
            "hours": 1.5,
            "notes": "Worked on tranche-22",
        },
        credentials={"harvest_api": _CRED_ID},
    )
    await HarvestNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["project_id"] == 100
    assert body["task_id"] == 200
    assert body["spent_date"] == "2026-04-23"
    assert body["hours"] == 1.5
    assert body["notes"] == "Worked on tranche-22"


@respx.mock
async def test_create_time_entry_with_timer_window() -> None:
    route = respx.post(f"{_API}/v2/time_entries").mock(
        return_value=Response(201, json={"id": 1}),
    )
    node = Node(
        id="node_1",
        name="Harvest",
        type="weftlyflow.harvest",
        parameters={
            "operation": "create_time_entry",
            "project_id": "100",
            "task_id": "200",
            "spent_date": "2026-04-23",
            "started_time": "09:00",
            "ended_time": "10:30",
        },
        credentials={"harvest_api": _CRED_ID},
    )
    await HarvestNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["started_time"] == "09:00"
    assert body["ended_time"] == "10:30"
    assert "hours" not in body


def test_create_time_entry_requires_hours_or_started_time() -> None:
    with pytest.raises(ValueError, match="'hours' or 'started_time'"):
        build_request(
            "create_time_entry",
            {
                "project_id": 1,
                "task_id": 2,
                "spent_date": "2026-04-23",
            },
        )


def test_create_time_entry_requires_project_id() -> None:
    with pytest.raises(ValueError, match="'project_id' is required"):
        build_request(
            "create_time_entry",
            {"task_id": 2, "spent_date": "2026-04-23", "hours": 1.0},
        )


# --- list_projects -------------------------------------------------


@respx.mock
async def test_list_projects_encodes_is_active_as_lowercase_string() -> None:
    route = respx.get(f"{_API}/v2/projects").mock(
        return_value=Response(200, json={"projects": []}),
    )
    node = Node(
        id="node_1",
        name="Harvest",
        type="weftlyflow.harvest",
        parameters={"operation": "list_projects", "is_active": True},
        credentials={"harvest_api": _CRED_ID},
    )
    await HarvestNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.url.params["is_active"] == "true"


# --- get_user_me ---------------------------------------------------


@respx.mock
async def test_get_user_me_round_trip() -> None:
    route = respx.get(f"{_API}/v2/users/me").mock(
        return_value=Response(200, json={"id": 1, "email": "a@b.c"}),
    )
    node = Node(
        id="node_1",
        name="Harvest",
        type="weftlyflow.harvest",
        parameters={"operation": "get_user_me"},
        credentials={"harvest_api": _CRED_ID},
    )
    await HarvestNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert sent.headers["Harvest-Account-ID"] == _ACCOUNT_ID


# --- errors --------------------------------------------------------


@respx.mock
async def test_api_error_is_parsed() -> None:
    respx.get(f"{_API}/v2/users/me").mock(
        return_value=Response(
            401,
            json={"error": "invalid_token", "error_description": "token has expired"},
        ),
    )
    node = Node(
        id="node_1",
        name="Harvest",
        type="weftlyflow.harvest",
        parameters={"operation": "get_user_me"},
        credentials={"harvest_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="token has expired"):
        await HarvestNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Harvest",
        type="weftlyflow.harvest",
        parameters={"operation": "get_user_me"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await HarvestNode().execute(_ctx_for(node), [Item()])


async def test_empty_account_id_raises() -> None:
    resolver = _resolver(account_id="")
    node = Node(
        id="node_1",
        name="Harvest",
        type="weftlyflow.harvest",
        parameters={"operation": "get_user_me"},
        credentials={"harvest_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'account_id'"):
        await HarvestNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
