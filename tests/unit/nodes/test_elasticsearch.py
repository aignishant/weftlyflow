"""Unit tests for :class:`ElasticsearchNode`.

Exercises every supported operation against a respx-mocked cluster.
Verifies the distinctive ``Authorization: ApiKey <b64(id:key)>`` scheme,
the per-cluster base URL from the credential, the ndjson body shape of
the bulk endpoint, and the ``error.type: error.reason`` envelope parse.
"""

from __future__ import annotations

import json
from base64 import b64decode

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import ElasticsearchApiCredential
from weftlyflow.credentials.types.elasticsearch_api import base_url_from
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.elasticsearch import ElasticsearchNode
from weftlyflow.nodes.integrations.elasticsearch.operations import build_request

_CRED_ID: str = "cr_es"
_PROJECT_ID: str = "pr_test"
_BASE_URL: str = "https://es.example.com:9243"
_KEY_ID: str = "kid-1"
_API_KEY: str = "shh-secret"


def _resolver() -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.elasticsearch_api": ElasticsearchApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.elasticsearch_api",
                {"api_key_id": _KEY_ID, "api_key": _API_KEY, "base_url": _BASE_URL},
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


# --- search -----------------------------------------------------------


@respx.mock
async def test_search_sends_apikey_header_not_bearer_or_basic() -> None:
    route = respx.post(f"{_BASE_URL}/books/_search").mock(
        return_value=Response(200, json={"hits": {"hits": []}}),
    )
    node = Node(
        id="node_1",
        name="ES",
        type="weftlyflow.elasticsearch",
        parameters={
            "operation": "search",
            "index": "books",
            "query": {"match": {"title": "dune"}},
            "size": 5,
        },
        credentials={"elasticsearch_api": _CRED_ID},
    )
    await ElasticsearchNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    auth = request.headers["Authorization"]
    assert auth.startswith("ApiKey ")
    assert "Bearer" not in auth
    assert "Basic" not in auth
    decoded = b64decode(auth.split(" ", 1)[1]).decode()
    assert decoded == f"{_KEY_ID}:{_API_KEY}"
    body = json.loads(request.content)
    assert body["size"] == 5
    assert body["query"] == {"match": {"title": "dune"}}


@respx.mock
async def test_search_defaults_to_match_all_query() -> None:
    route = respx.post(f"{_BASE_URL}/books/_search").mock(
        return_value=Response(200, json={"hits": {"hits": []}}),
    )
    node = Node(
        id="node_1",
        name="ES",
        type="weftlyflow.elasticsearch",
        parameters={"operation": "search", "index": "books"},
        credentials={"elasticsearch_api": _CRED_ID},
    )
    await ElasticsearchNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["query"] == {"match_all": {}}


# --- index ------------------------------------------------------------


@respx.mock
async def test_index_with_id_uses_put_and_doc_path() -> None:
    route = respx.put(f"{_BASE_URL}/books/_doc/42").mock(
        return_value=Response(201, json={"_id": "42"}),
    )
    node = Node(
        id="node_1",
        name="ES",
        type="weftlyflow.elasticsearch",
        parameters={
            "operation": "index",
            "index": "books",
            "id": "42",
            "document": {"title": "Dune"},
            "refresh": "wait_for",
        },
        credentials={"elasticsearch_api": _CRED_ID},
    )
    await ElasticsearchNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert "refresh=wait_for" in str(request.url)
    assert json.loads(request.content) == {"title": "Dune"}


@respx.mock
async def test_index_without_id_uses_post() -> None:
    route = respx.post(f"{_BASE_URL}/books/_doc").mock(
        return_value=Response(201, json={"_id": "auto"}),
    )
    node = Node(
        id="node_1",
        name="ES",
        type="weftlyflow.elasticsearch",
        parameters={
            "operation": "index",
            "index": "books",
            "document": {"title": "Auto"},
        },
        credentials={"elasticsearch_api": _CRED_ID},
    )
    await ElasticsearchNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- bulk -------------------------------------------------------------


@respx.mock
async def test_bulk_sends_ndjson_content_type_and_body() -> None:
    route = respx.post(f"{_BASE_URL}/books/_bulk").mock(
        return_value=Response(200, json={"errors": False, "items": []}),
    )
    node = Node(
        id="node_1",
        name="ES",
        type="weftlyflow.elasticsearch",
        parameters={
            "operation": "bulk",
            "index": "books",
            "actions": [
                {"action": {"index": {"_id": "1"}}, "doc": {"title": "A"}},
                {"action": {"delete": {"_id": "2"}}},
            ],
        },
        credentials={"elasticsearch_api": _CRED_ID},
    )
    await ElasticsearchNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Content-Type"] == "application/x-ndjson"
    body = request.content.decode()
    lines = body.rstrip("\n").split("\n")
    assert lines == [
        '{"index":{"_id":"1"}}',
        '{"title":"A"}',
        '{"delete":{"_id":"2"}}',
    ]
    assert body.endswith("\n")


def test_bulk_rejects_missing_action() -> None:
    with pytest.raises(ValueError, match="missing 'action' object"):
        build_request("bulk", {"index": "books", "actions": [{"doc": {"x": 1}}]})


def test_bulk_rejects_non_list_actions() -> None:
    with pytest.raises(ValueError, match="non-empty list"):
        build_request("bulk", {"index": "books", "actions": "nope"})


# --- update / delete / get --------------------------------------------


@respx.mock
async def test_update_requires_doc_or_script() -> None:
    node = Node(
        id="node_1",
        name="ES",
        type="weftlyflow.elasticsearch",
        parameters={"operation": "update", "index": "books", "id": "1"},
        credentials={"elasticsearch_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="requires 'document' or 'script'"):
        await ElasticsearchNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_delete_sends_delete_verb() -> None:
    route = respx.delete(f"{_BASE_URL}/books/_doc/7").mock(
        return_value=Response(200, json={"result": "deleted"}),
    )
    node = Node(
        id="node_1",
        name="ES",
        type="weftlyflow.elasticsearch",
        parameters={"operation": "delete", "index": "books", "id": "7"},
        credentials={"elasticsearch_api": _CRED_ID},
    )
    await ElasticsearchNode().execute(_ctx_for(node), [Item()])
    assert route.called


@respx.mock
async def test_get_returns_document_envelope() -> None:
    respx.get(f"{_BASE_URL}/books/_doc/7").mock(
        return_value=Response(200, json={"_id": "7", "_source": {"title": "Dune"}}),
    )
    node = Node(
        id="node_1",
        name="ES",
        type="weftlyflow.elasticsearch",
        parameters={"operation": "get", "index": "books", "id": "7"},
        credentials={"elasticsearch_api": _CRED_ID},
    )
    out = await ElasticsearchNode().execute(_ctx_for(node), [Item()])
    assert out[0][0].json["response"]["_source"]["title"] == "Dune"


# --- base URL normalization -------------------------------------------


def test_base_url_from_adds_https_if_missing() -> None:
    assert base_url_from("cluster.local:9200") == "https://cluster.local:9200"


def test_base_url_from_strips_trailing_slash() -> None:
    assert base_url_from("https://es.x.io/") == "https://es.x.io"


def test_base_url_from_rejects_empty() -> None:
    with pytest.raises(ValueError, match="'base_url' is required"):
        base_url_from("   ")


# --- errors -----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_type_and_reason() -> None:
    respx.post(f"{_BASE_URL}/books/_search").mock(
        return_value=Response(
            400,
            json={
                "error": {
                    "type": "parsing_exception",
                    "reason": "malformed query",
                },
            },
        ),
    )
    node = Node(
        id="node_1",
        name="ES",
        type="weftlyflow.elasticsearch",
        parameters={"operation": "search", "index": "books"},
        credentials={"elasticsearch_api": _CRED_ID},
    )
    with pytest.raises(
        NodeExecutionError, match="parsing_exception: malformed query",
    ):
        await ElasticsearchNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="ES",
        type="weftlyflow.elasticsearch",
        parameters={"operation": "search", "index": "books"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await ElasticsearchNode().execute(_ctx_for(node), [Item()])


# --- direct builder unit tests ----------------------------------------


def test_build_search_caps_size() -> None:
    _, _, body, _, _ = build_request("search", {"index": "x", "size": 999_999})
    assert body["size"] == 10_000


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("reindex_the_planet", {})
