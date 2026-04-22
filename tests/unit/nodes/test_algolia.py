"""Unit tests for :class:`AlgoliaNode`.

Exercises every supported operation against a respx-mocked Algolia
Search v1 API. Verifies the dual ``X-Algolia-Application-Id`` /
``X-Algolia-API-Key`` headers, the split between search-DSN host
(reads) and write host (indexing), and the ``hits_per_page`` cap.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import AlgoliaApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.algolia import AlgoliaNode
from weftlyflow.nodes.integrations.algolia.operations import build_request

_CRED_ID: str = "cr_alg"
_PROJECT_ID: str = "pr_test"
_APP_ID: str = "APP123"
_READ_BASE: str = f"https://{_APP_ID}-dsn.algolia.net/1"
_WRITE_BASE: str = f"https://{_APP_ID}.algolia.net/1"


def _resolver(
    *,
    app_id: str = _APP_ID,
    api_key: str = "k-secret",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.algolia_api": AlgoliaApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.algolia_api",
                {"application_id": app_id, "api_key": api_key},
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


# --- search (read host) -------------------------------------------------


@respx.mock
async def test_search_hits_dsn_host_with_both_headers_and_body() -> None:
    route = respx.post(f"{_READ_BASE}/indexes/products/query").mock(
        return_value=Response(200, json={"hits": [{"objectID": "o1"}]}),
    )
    node = Node(
        id="node_1",
        name="Algolia",
        type="weftlyflow.algolia",
        parameters={
            "operation": "search",
            "index_name": "products",
            "query": "shoes",
            "filters": "category:men",
            "page": 2,
            "hits_per_page": 10,
            "extra_params": {"typoTolerance": "strict"},
        },
        credentials={"algolia_api": _CRED_ID},
    )
    out = await AlgoliaNode().execute(
        _ctx_for(node, resolver=_resolver()), [Item()],
    )
    request = route.calls.last.request
    assert request.headers["X-Algolia-Application-Id"] == _APP_ID
    assert request.headers["X-Algolia-API-Key"] == "k-secret"
    body = json.loads(request.content)
    assert body == {
        "query": "shoes",
        "hitsPerPage": 10,
        "page": 2,
        "filters": "category:men",
        "typoTolerance": "strict",
    }
    [result] = out[0]
    assert result.json["hits"] == [{"objectID": "o1"}]


async def test_search_rejects_non_dict_extra_params() -> None:
    node = Node(
        id="node_1",
        name="Algolia",
        type="weftlyflow.algolia",
        parameters={
            "operation": "search",
            "index_name": "products",
            "extra_params": "not-a-dict",
        },
        credentials={"algolia_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="extra_params"):
        await AlgoliaNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- add_object (write host) --------------------------------------------


@respx.mock
async def test_add_object_targets_write_host() -> None:
    route = respx.post(f"{_WRITE_BASE}/indexes/products").mock(
        return_value=Response(201, json={"objectID": "o1"}),
    )
    node = Node(
        id="node_1",
        name="Algolia",
        type="weftlyflow.algolia",
        parameters={
            "operation": "add_object",
            "index_name": "products",
            "object": {"name": "sneaker"},
        },
        credentials={"algolia_api": _CRED_ID},
    )
    await AlgoliaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body == {"name": "sneaker"}


async def test_add_object_requires_non_empty_object() -> None:
    node = Node(
        id="node_1",
        name="Algolia",
        type="weftlyflow.algolia",
        parameters={
            "operation": "add_object",
            "index_name": "products",
            "object": {},
        },
        credentials={"algolia_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'object'"):
        await AlgoliaNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


# --- update_object ------------------------------------------------------


@respx.mock
async def test_update_object_puts_with_object_id_merged_into_body() -> None:
    route = respx.put(f"{_WRITE_BASE}/indexes/products/o1").mock(
        return_value=Response(200, json={"updatedAt": "now"}),
    )
    node = Node(
        id="node_1",
        name="Algolia",
        type="weftlyflow.algolia",
        parameters={
            "operation": "update_object",
            "index_name": "products",
            "object_id": "o1",
            "object": {"price": 99},
        },
        credentials={"algolia_api": _CRED_ID},
    )
    await AlgoliaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"price": 99, "objectID": "o1"}


# --- get_object (read host) ---------------------------------------------


@respx.mock
async def test_get_object_uses_read_host() -> None:
    route = respx.get(f"{_READ_BASE}/indexes/products/o1").mock(
        return_value=Response(200, json={"objectID": "o1"}),
    )
    node = Node(
        id="node_1",
        name="Algolia",
        type="weftlyflow.algolia",
        parameters={
            "operation": "get_object",
            "index_name": "products",
            "object_id": "o1",
        },
        credentials={"algolia_api": _CRED_ID},
    )
    await AlgoliaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- delete_object (write host) -----------------------------------------


@respx.mock
async def test_delete_object_uses_write_host() -> None:
    route = respx.delete(f"{_WRITE_BASE}/indexes/products/o1").mock(
        return_value=Response(200, json={"taskID": 42}),
    )
    node = Node(
        id="node_1",
        name="Algolia",
        type="weftlyflow.algolia",
        parameters={
            "operation": "delete_object",
            "index_name": "products",
            "object_id": "o1",
        },
        credentials={"algolia_api": _CRED_ID},
    )
    await AlgoliaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- list_indices -------------------------------------------------------


@respx.mock
async def test_list_indices_hits_read_host_at_root() -> None:
    route = respx.get(f"{_READ_BASE}/indexes").mock(
        return_value=Response(200, json={"items": [{"name": "products"}]}),
    )
    node = Node(
        id="node_1",
        name="Algolia",
        type="weftlyflow.algolia",
        parameters={"operation": "list_indices"},
        credentials={"algolia_api": _CRED_ID},
    )
    await AlgoliaNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- errors / credentials -----------------------------------------------


@respx.mock
async def test_api_error_surfaces_message_field() -> None:
    respx.post(f"{_READ_BASE}/indexes/products/query").mock(
        return_value=Response(400, json={"message": "bad filter"}),
    )
    node = Node(
        id="node_1",
        name="Algolia",
        type="weftlyflow.algolia",
        parameters={
            "operation": "search",
            "index_name": "products",
            "filters": "oops",
        },
        credentials={"algolia_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="bad filter"):
        await AlgoliaNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Algolia",
        type="weftlyflow.algolia",
        parameters={"operation": "list_indices"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await AlgoliaNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_empty_credential_fields_raise() -> None:
    node = Node(
        id="node_1",
        name="Algolia",
        type="weftlyflow.algolia",
        parameters={"operation": "list_indices"},
        credentials={"algolia_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="application_id"):
        await AlgoliaNode().execute(
            _ctx_for(node, resolver=_resolver(app_id="")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_request_search_caps_hits_per_page_at_max() -> None:
    _, _, body, _, use_write = build_request(
        "search", {"index_name": "i", "hits_per_page": 9_999},
    )
    assert body is not None
    assert body["hitsPerPage"] == 1000
    assert use_write is False


def test_build_request_add_object_flags_write_host() -> None:
    _, _, _, _, use_write = build_request(
        "add_object", {"index_name": "i", "object": {"a": 1}},
    )
    assert use_write is True


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("clear_index", {})
