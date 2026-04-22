"""Unit tests for :class:`TrelloNode`.

Exercises every supported operation against a respx-mocked Trello v1
REST API. Verifies that ``key`` and ``token`` are appended to every
request as query parameters (not sent as headers or in a body).
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import TrelloApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.trello import TrelloNode
from weftlyflow.nodes.integrations.trello.operations import build_request

_CRED_ID: str = "cr_trello"
_PROJECT_ID: str = "pr_test"
_BASE_URL: str = "https://api.trello.com"


def _resolver(
    *,
    api_key: str = "k_abc",
    api_token: str = "t_xyz",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.trello_api": TrelloApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.trello_api",
                {"api_key": api_key, "api_token": api_token},
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


def _query(request: object) -> dict[str, str]:
    return dict(request.url.params)  # type: ignore[attr-defined]


# --- get_board / list_cards ----------------------------------------------


@respx.mock
async def test_get_board_appends_key_and_token_as_query_params() -> None:
    route = respx.get(f"{_BASE_URL}/1/boards/board1").mock(
        return_value=Response(200, json={"id": "board1", "name": "Work"}),
    )
    node = Node(
        id="node_1",
        name="Trello",
        type="weftlyflow.trello",
        parameters={"operation": "get_board", "board_id": "board1"},
        credentials={"trello_api": _CRED_ID},
    )
    out = await TrelloNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["id"] == "board1"
    request = route.calls.last.request
    query = _query(request)
    assert query["key"] == "k_abc"
    assert query["token"] == "t_xyz"
    assert "authorization" not in request.headers


@respx.mock
async def test_list_cards_surfaces_cards_convenience_key() -> None:
    route = respx.get(f"{_BASE_URL}/1/boards/board1/cards").mock(
        return_value=Response(
            200,
            json=[{"id": "c1", "name": "A"}, {"id": "c2", "name": "B"}],
        ),
    )
    node = Node(
        id="node_1",
        name="Trello",
        type="weftlyflow.trello",
        parameters={
            "operation": "list_cards",
            "board_id": "board1",
            "filter": "open",
        },
        credentials={"trello_api": _CRED_ID},
    )
    out = await TrelloNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [c["id"] for c in result.json["cards"]] == ["c1", "c2"]
    query = _query(route.calls.last.request)
    assert query["filter"] == "open"


# --- create / update / get / delete card ---------------------------------


@respx.mock
async def test_create_card_posts_with_query_params_only() -> None:
    route = respx.post(f"{_BASE_URL}/1/cards").mock(
        return_value=Response(200, json={"id": "c1", "name": "New"}),
    )
    node = Node(
        id="node_1",
        name="Trello",
        type="weftlyflow.trello",
        parameters={
            "operation": "create_card",
            "list_id": "list1",
            "name": "New",
            "extra_fields": {"desc": "body", "idLabels": ["L1", "L2"]},
        },
        credentials={"trello_api": _CRED_ID},
    )
    await TrelloNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    query = _query(request)
    assert query["idList"] == "list1"
    assert query["name"] == "New"
    assert query["desc"] == "body"
    assert query["idLabels"] == "L1,L2"
    assert request.content in (b"", b"null")


@respx.mock
async def test_update_card_uses_put_with_fields() -> None:
    route = respx.put(f"{_BASE_URL}/1/cards/c1").mock(
        return_value=Response(200, json={"id": "c1"}),
    )
    node = Node(
        id="node_1",
        name="Trello",
        type="weftlyflow.trello",
        parameters={
            "operation": "update_card",
            "card_id": "c1",
            "fields": {"name": "Renamed", "closed": True},
        },
        credentials={"trello_api": _CRED_ID},
    )
    await TrelloNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    query = _query(route.calls.last.request)
    assert query["name"] == "Renamed"
    assert query["closed"] == "true"


@respx.mock
async def test_get_card_is_a_get() -> None:
    route = respx.get(f"{_BASE_URL}/1/cards/c1").mock(
        return_value=Response(200, json={"id": "c1"}),
    )
    node = Node(
        id="node_1",
        name="Trello",
        type="weftlyflow.trello",
        parameters={"operation": "get_card", "card_id": "c1"},
        credentials={"trello_api": _CRED_ID},
    )
    await TrelloNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


@respx.mock
async def test_delete_card_is_a_delete() -> None:
    route = respx.delete(f"{_BASE_URL}/1/cards/c1").mock(
        return_value=Response(200, json={"_value": None}),
    )
    node = Node(
        id="node_1",
        name="Trello",
        type="weftlyflow.trello",
        parameters={"operation": "delete_card", "card_id": "c1"},
        credentials={"trello_api": _CRED_ID},
    )
    await TrelloNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- error paths ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_plain_text() -> None:
    respx.get(f"{_BASE_URL}/1/boards/bad").mock(
        return_value=Response(401, text="invalid key"),
    )
    node = Node(
        id="node_1",
        name="Trello",
        type="weftlyflow.trello",
        parameters={"operation": "get_board", "board_id": "bad"},
        credentials={"trello_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid key"):
        await TrelloNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Trello",
        type="weftlyflow.trello",
        parameters={"operation": "get_board", "board_id": "b"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await TrelloNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_incomplete_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Trello",
        type="weftlyflow.trello",
        parameters={"operation": "get_board", "board_id": "b"},
        credentials={"trello_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'api_key' and 'api_token'"):
        await TrelloNode().execute(
            _ctx_for(node, resolver=_resolver(api_token="")), [Item()],
        )


# --- direct builder unit tests --------------------------------------------


def test_build_request_create_card_requires_name() -> None:
    with pytest.raises(ValueError, match="'name' is required"):
        build_request("create_card", {"list_id": "l1"})


def test_build_request_update_card_rejects_empty_fields() -> None:
    with pytest.raises(ValueError, match="'fields'"):
        build_request("update_card", {"card_id": "c1", "fields": {}})


def test_build_request_update_card_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match="unknown card field"):
        build_request(
            "update_card",
            {"card_id": "c1", "fields": {"bogus": "x"}},
        )


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("eat_lunch", {})
