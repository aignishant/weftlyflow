"""Unit tests for :class:`DropboxNode`.

Exercises every supported operation against a respx-mocked Dropbox API.
Verifies the Bearer header, the split RPC (``api.dropboxapi.com``) vs
content (``content.dropboxapi.com``) endpoints, the distinctive
JSON-encoded ``Dropbox-API-Arg`` header used for the download endpoint,
the path-prefix validation (``/``, ``id:``, ``rev:``), and the
``error_summary`` error-envelope parse.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import DropboxApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.dropbox import DropboxNode
from weftlyflow.nodes.integrations.dropbox.operations import build_request

_CRED_ID: str = "cr_dbx"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "dbx-secret"
_API: str = "https://api.dropboxapi.com"
_CONTENT: str = "https://content.dropboxapi.com"


def _resolver() -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.dropbox_api": DropboxApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.dropbox_api",
                {"access_token": _TOKEN},
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


# --- list_folder -----------------------------------------------------


@respx.mock
async def test_list_folder_posts_to_rpc_host_with_bearer() -> None:
    route = respx.post(f"{_API}/2/files/list_folder").mock(
        return_value=Response(200, json={"entries": []}),
    )
    node = Node(
        id="node_1",
        name="Dropbox",
        type="weftlyflow.dropbox",
        parameters={"operation": "list_folder", "path": "/reports", "recursive": True},
        credentials={"dropbox_api": _CRED_ID},
    )
    await DropboxNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert "Dropbox-API-Arg" not in request.headers
    body = json.loads(request.content)
    assert body == {"path": "/reports", "recursive": True}


# --- get_metadata / create_folder / delete ---------------------------


@respx.mock
async def test_create_folder_v2_endpoint() -> None:
    route = respx.post(f"{_API}/2/files/create_folder_v2").mock(
        return_value=Response(200, json={"metadata": {"name": "new"}}),
    )
    node = Node(
        id="node_1",
        name="Dropbox",
        type="weftlyflow.dropbox",
        parameters={"operation": "create_folder", "path": "/new", "autorename": True},
        credentials={"dropbox_api": _CRED_ID},
    )
    await DropboxNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"path": "/new", "autorename": True}


@respx.mock
async def test_delete_v2_endpoint() -> None:
    route = respx.post(f"{_API}/2/files/delete_v2").mock(
        return_value=Response(200, json={"metadata": {}}),
    )
    node = Node(
        id="node_1",
        name="Dropbox",
        type="weftlyflow.dropbox",
        parameters={"operation": "delete", "path": "/old.txt"},
        credentials={"dropbox_api": _CRED_ID},
    )
    await DropboxNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- move / copy -----------------------------------------------------


@respx.mock
async def test_move_uses_from_and_to_paths() -> None:
    route = respx.post(f"{_API}/2/files/move_v2").mock(
        return_value=Response(200, json={"metadata": {}}),
    )
    node = Node(
        id="node_1",
        name="Dropbox",
        type="weftlyflow.dropbox",
        parameters={
            "operation": "move",
            "from_path": "/a.txt",
            "to_path": "/b.txt",
            "allow_shared_folder": True,
        },
        credentials={"dropbox_api": _CRED_ID},
    )
    await DropboxNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["from_path"] == "/a.txt"
    assert body["to_path"] == "/b.txt"
    assert body["allow_shared_folder"] is True


@respx.mock
async def test_copy_v2_endpoint() -> None:
    route = respx.post(f"{_API}/2/files/copy_v2").mock(
        return_value=Response(200, json={"metadata": {}}),
    )
    node = Node(
        id="node_1",
        name="Dropbox",
        type="weftlyflow.dropbox",
        parameters={
            "operation": "copy",
            "from_path": "/a.txt",
            "to_path": "/backup/a.txt",
        },
        credentials={"dropbox_api": _CRED_ID},
    )
    await DropboxNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- search ----------------------------------------------------------


@respx.mock
async def test_search_wraps_query_in_options_envelope() -> None:
    route = respx.post(f"{_API}/2/files/search_v2").mock(
        return_value=Response(200, json={"matches": []}),
    )
    node = Node(
        id="node_1",
        name="Dropbox",
        type="weftlyflow.dropbox",
        parameters={
            "operation": "search",
            "query": "report",
            "limit": 25,
            "path": "/reports",
        },
        credentials={"dropbox_api": _CRED_ID},
    )
    await DropboxNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["query"] == "report"
    assert body["options"]["max_results"] == 25
    assert body["options"]["path"] == "/reports"


# --- download (content endpoint, Dropbox-API-Arg) --------------------


@respx.mock
async def test_download_targets_content_host_with_arg_header() -> None:
    route = respx.post(f"{_CONTENT}/2/files/download").mock(
        return_value=Response(
            200,
            content=b"file-bytes",
            headers={
                "Dropbox-API-Result": json.dumps({"name": "doc.pdf", "size": 10}),
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Dropbox",
        type="weftlyflow.dropbox",
        parameters={"operation": "download", "path": "/docs/doc.pdf"},
        credentials={"dropbox_api": _CRED_ID},
    )
    out = await DropboxNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    arg = request.headers["Dropbox-API-Arg"]
    assert json.loads(arg) == {"path": "/docs/doc.pdf"}
    assert request.content == b""
    result = out[0][0].json
    assert result["operation"] == "download"
    assert result["response"] == {"name": "doc.pdf", "size": 10}
    assert result["content_length"] == len(b"file-bytes")


# --- path validation -------------------------------------------------


def test_required_path_rejects_missing_slash_prefix() -> None:
    with pytest.raises(ValueError, match="must start with"):
        build_request("list_folder", {"path": "no-prefix"})


def test_required_path_accepts_id_prefix() -> None:
    _, path, body, _ = build_request("get_metadata", {"path": "id:abc123"})
    assert body == {"path": "id:abc123"}
    assert path == "/2/files/get_metadata"


def test_required_path_accepts_rev_prefix() -> None:
    _, _, body, _ = build_request("get_metadata", {"path": "rev:abcd"})
    assert body == {"path": "rev:abcd"}


def test_required_path_rejects_empty() -> None:
    with pytest.raises(ValueError, match="'path' is required"):
        build_request("list_folder", {})


# --- search builder edge cases ---------------------------------------


def test_search_coerces_limit_to_int() -> None:
    _, _, body, _ = build_request("search", {"query": "x", "limit": "42"})
    assert body["options"]["max_results"] == 42


def test_search_rejects_non_integer_limit() -> None:
    with pytest.raises(ValueError, match="'limit' must be a positive integer"):
        build_request("search", {"query": "x", "limit": "bogus"})


def test_search_caps_limit_at_maximum() -> None:
    _, _, body, _ = build_request("search", {"query": "x", "limit": 999_999})
    assert body["options"]["max_results"] == 1_000


def test_search_defaults_limit_when_missing() -> None:
    _, _, body, _ = build_request("search", {"query": "x"})
    assert body["options"]["max_results"] == 100


# --- errors ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_error_summary() -> None:
    respx.post(f"{_API}/2/files/get_metadata").mock(
        return_value=Response(
            409,
            json={
                "error_summary": "path/not_found/.",
                "error": {".tag": "path"},
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Dropbox",
        type="weftlyflow.dropbox",
        parameters={"operation": "get_metadata", "path": "/missing"},
        credentials={"dropbox_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="path/not_found"):
        await DropboxNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Dropbox",
        type="weftlyflow.dropbox",
        parameters={"operation": "list_folder", "path": "/"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await DropboxNode().execute(_ctx_for(node), [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("eject_all_disks", {})
