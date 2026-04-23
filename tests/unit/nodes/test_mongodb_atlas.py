"""Unit tests for :class:`MongoDbAtlasNode` and ``MongoDbAtlasApiCredential``.

Atlas is the catalog's first HTTP Digest integration — credentials
cannot be precomputed into a header, so :meth:`inject` is a no-op and
the node instead wires :class:`httpx.DigestAuth` onto its
:class:`httpx.AsyncClient`. Tests verify both the Digest handshake
(401 challenge → authenticated retry) and the path-variable shape of
Atlas URLs.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import MongoDbAtlasApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.mongodb_atlas import MongoDbAtlasNode
from weftlyflow.nodes.integrations.mongodb_atlas.operations import build_request

_CRED_ID: str = "cr_atlas"
_PROJECT_ID: str = "pr_test"
_PUBLIC: str = "abcdefgh"
_PRIVATE: str = "11111111-2222-3333-4444-555555555555"
_API: str = "https://cloud.mongodb.com/api/atlas/v2"
_GROUP: str = "5e2211c17a3e5a48f5497de3"
_CLUSTER: str = "Cluster0"
_CHALLENGE: str = (
    'Digest realm="MMS Public API", '
    'nonce="YWJjZGVmZ2hpamtsbW5vcA==", '
    'qop="auth", algorithm=MD5'
)


def _resolver(
    *, public_key: str = _PUBLIC, private_key: str = _PRIVATE,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.mongodb_atlas_api": MongoDbAtlasApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.mongodb_atlas_api",
                {"public_key": public_key, "private_key": private_key},
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


# --- credential: inject is a no-op --------------------------------


async def test_credential_inject_is_no_op() -> None:
    request = httpx.Request("GET", f"{_API}/groups")
    out = await MongoDbAtlasApiCredential().inject(
        {"public_key": _PUBLIC, "private_key": _PRIVATE}, request,
    )
    assert "Authorization" not in out.headers


# --- Digest handshake ---------------------------------------------


@respx.mock
async def test_list_projects_completes_digest_handshake() -> None:
    route = respx.get(f"{_API}/groups").mock(
        side_effect=[
            Response(401, headers={"WWW-Authenticate": _CHALLENGE}),
            Response(200, json={"results": [{"id": _GROUP, "name": "prod"}]}),
        ],
    )
    node = Node(
        id="node_1",
        name="Atlas",
        type="weftlyflow.mongodb_atlas",
        parameters={"operation": "list_projects"},
        credentials={"mongodb_atlas_api": _CRED_ID},
    )
    await MongoDbAtlasNode().execute(_ctx_for(node), [Item()])
    assert route.call_count == 2
    second = route.calls[1].request
    assert second.headers["Authorization"].startswith("Digest ")
    assert f'username="{_PUBLIC}"' in second.headers["Authorization"]
    assert second.headers["Accept"].startswith("application/vnd.atlas.")


# --- path-variable operations -------------------------------------


@respx.mock
async def test_list_clusters_embeds_group_id_in_path() -> None:
    route = respx.get(f"{_API}/groups/{_GROUP}/clusters").mock(
        return_value=Response(200, json={"results": []}),
    )
    node = Node(
        id="node_1",
        name="Atlas",
        type="weftlyflow.mongodb_atlas",
        parameters={"operation": "list_clusters", "group_id": _GROUP},
        credentials={"mongodb_atlas_api": _CRED_ID},
    )
    await MongoDbAtlasNode().execute(_ctx_for(node), [Item()])
    assert route.called


@respx.mock
async def test_get_cluster_embeds_both_ids_in_path() -> None:
    route = respx.get(f"{_API}/groups/{_GROUP}/clusters/{_CLUSTER}").mock(
        return_value=Response(200, json={"id": "c1", "name": _CLUSTER}),
    )
    node = Node(
        id="node_1",
        name="Atlas",
        type="weftlyflow.mongodb_atlas",
        parameters={
            "operation": "get_cluster",
            "group_id": _GROUP,
            "cluster_name": _CLUSTER,
        },
        credentials={"mongodb_atlas_api": _CRED_ID},
    )
    await MongoDbAtlasNode().execute(_ctx_for(node), [Item()])
    assert route.called


@respx.mock
async def test_list_db_users_forwards_paging_as_query_params() -> None:
    route = respx.get(f"{_API}/groups/{_GROUP}/databaseUsers").mock(
        return_value=Response(200, json={"results": []}),
    )
    node = Node(
        id="node_1",
        name="Atlas",
        type="weftlyflow.mongodb_atlas",
        parameters={
            "operation": "list_db_users",
            "group_id": _GROUP,
            "page_num": 2,
            "items_per_page": 100,
        },
        credentials={"mongodb_atlas_api": _CRED_ID},
    )
    await MongoDbAtlasNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    assert sent.url.params["pageNum"] == "2"
    assert sent.url.params["itemsPerPage"] == "100"


# --- validation ---------------------------------------------------


def test_list_clusters_requires_group_id() -> None:
    with pytest.raises(ValueError, match="'group_id' is required"):
        build_request("list_clusters", {})


def test_get_cluster_requires_cluster_name() -> None:
    with pytest.raises(ValueError, match="'cluster_name' is required"):
        build_request("get_cluster", {"group_id": _GROUP})


# --- errors --------------------------------------------------------


@respx.mock
async def test_atlas_error_message_is_parsed() -> None:
    respx.get(f"{_API}/groups/{_GROUP}/clusters").mock(
        return_value=Response(
            404,
            json={
                "detail": "No group with ID " + _GROUP + " exists.",
                "errorCode": "GROUP_NOT_FOUND",
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Atlas",
        type="weftlyflow.mongodb_atlas",
        parameters={"operation": "list_clusters", "group_id": _GROUP},
        credentials={"mongodb_atlas_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="No group with ID"):
        await MongoDbAtlasNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Atlas",
        type="weftlyflow.mongodb_atlas",
        parameters={"operation": "list_projects"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await MongoDbAtlasNode().execute(_ctx_for(node), [Item()])


async def test_empty_public_key_raises() -> None:
    resolver = _resolver(public_key="")
    node = Node(
        id="node_1",
        name="Atlas",
        type="weftlyflow.mongodb_atlas",
        parameters={"operation": "list_projects"},
        credentials={"mongodb_atlas_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'public_key' or 'private_key'"):
        await MongoDbAtlasNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
