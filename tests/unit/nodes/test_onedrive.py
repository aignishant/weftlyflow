"""Unit tests for :class:`OneDriveNode` (reuses ``MicrosoftGraphCredential``).

Exercises the path-vs-item addressing split on the ``/me/drive`` root,
the small-upload direct PUT to ``/root:/{path}:/content``, and — most
distinctive — the two-step session-based large upload:

    1. POST ``/createUploadSession`` → returns ``uploadUrl``.
    2. PUT successive byte ranges to the ``uploadUrl`` (outside Graph,
       no Authorization header), each carrying
       ``Content-Range: bytes X-Y/TOTAL`` and ``Content-Length``.

The final chunk's response payload is what the node reports.
"""

from __future__ import annotations

import base64

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
from weftlyflow.nodes.integrations.onedrive import OneDriveNode
from weftlyflow.nodes.integrations.onedrive.operations import build_request

_CRED_ID: str = "cr_onedrive"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "eyJ0eXAi.ms-graph-token"
_GRAPH: str = "https://graph.microsoft.com/v1.0/me/drive"
_UPLOAD_URL: str = "https://upload.example.com/session/abc"
_CHUNK_SIZE: int = 320 * 1024  # 320 KiB — the Graph alignment boundary


def _resolver(*, token: str = _TOKEN) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.microsoft_graph": MicrosoftGraphCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.microsoft_graph",
                {"access_token": token, "tenant_id": "t1"},
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


# --- list_children --------------------------------------------------


@respx.mock
async def test_list_children_on_root_when_folder_empty() -> None:
    route = respx.get(f"{_GRAPH}/root/children").mock(
        return_value=Response(200, json={"value": []}),
    )
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={"operation": "list_children"},
        credentials={"microsoft_graph": _CRED_ID},
    )
    await OneDriveNode().execute(_ctx_for(node), [Item()])
    assert route.called
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {_TOKEN}"


@respx.mock
async def test_list_children_of_path_encodes_segments() -> None:
    route = respx.get(f"{_GRAPH}/root:/folder%20with%20space/sub:/children").mock(
        return_value=Response(200, json={"value": []}),
    )
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={
            "operation": "list_children",
            "folder_path": "folder with space/sub",
            "$top": 10,
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    await OneDriveNode().execute(_ctx_for(node), [Item()])
    assert route.called
    assert route.calls.last.request.url.params["$top"] == "10"


# --- get_item / delete_item: path vs item_id -----------------------


@respx.mock
async def test_get_item_by_item_id_uses_items_endpoint() -> None:
    route = respx.get(f"{_GRAPH}/items/AB123").mock(
        return_value=Response(200, json={"id": "AB123"}),
    )
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={"operation": "get_item", "item_id": "AB123"},
        credentials={"microsoft_graph": _CRED_ID},
    )
    await OneDriveNode().execute(_ctx_for(node), [Item()])
    assert route.called


@respx.mock
async def test_get_item_by_path_uses_root_colon_path() -> None:
    route = respx.get(f"{_GRAPH}/root:/docs/report.pdf:").mock(
        return_value=Response(200, json={"id": "xyz"}),
    )
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={"operation": "get_item", "file_path": "docs/report.pdf"},
        credentials={"microsoft_graph": _CRED_ID},
    )
    await OneDriveNode().execute(_ctx_for(node), [Item()])
    assert route.called


@respx.mock
async def test_delete_item_by_item_id() -> None:
    route = respx.delete(f"{_GRAPH}/items/AB123").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={"operation": "delete_item", "item_id": "AB123"},
        credentials={"microsoft_graph": _CRED_ID},
    )
    await OneDriveNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- upload_small: direct PUT to :/content -------------------------


@respx.mock
async def test_upload_small_puts_raw_bytes_to_content_path() -> None:
    route = respx.put(f"{_GRAPH}/root:/docs/hello.txt:/content").mock(
        return_value=Response(201, json={"id": "new"}),
    )
    content = b"small content"
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={
            "operation": "upload_small",
            "file_path": "docs/hello.txt",
            "content_base64": base64.b64encode(content).decode("ascii"),
            "conflict_behavior": "rename",
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    await OneDriveNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.content == content
    assert request.headers["Content-Type"] == "application/octet-stream"
    assert request.url.params["@microsoft.graph.conflictBehavior"] == "rename"


async def test_upload_small_rejects_invalid_base64() -> None:
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={
            "operation": "upload_small",
            "file_path": "x.bin",
            "content_base64": "not!base64",
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="not valid base64"):
        await OneDriveNode().execute(_ctx_for(node), [Item()])


async def test_upload_small_requires_content() -> None:
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={
            "operation": "upload_small",
            "file_path": "x.bin",
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'content_base64' is required"):
        await OneDriveNode().execute(_ctx_for(node), [Item()])


# --- upload_large: two-step session with Content-Range chunks -----


@respx.mock
async def test_upload_large_opens_session_then_streams_chunks() -> None:
    session_route = respx.post(
        f"{_GRAPH}/root:/docs/big.bin:/createUploadSession",
    ).mock(return_value=Response(200, json={"uploadUrl": _UPLOAD_URL}))
    total = _CHUNK_SIZE * 2 + 17  # two full chunks + remainder
    content = b"A" * total
    chunk_route = respx.put(_UPLOAD_URL)
    chunk_route.side_effect = [
        Response(202, json={"nextExpectedRanges": [f"{_CHUNK_SIZE}-"]}),
        Response(
            202,
            json={"nextExpectedRanges": [f"{2 * _CHUNK_SIZE}-"]},
        ),
        Response(201, json={"id": "big-id"}),
    ]

    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={
            "operation": "upload_large",
            "file_path": "docs/big.bin",
            "content_base64": base64.b64encode(content).decode("ascii"),
            "chunk_size_bytes": _CHUNK_SIZE,
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    results = await OneDriveNode().execute(_ctx_for(node), [Item()])

    assert session_route.called
    assert chunk_route.call_count == 3

    # Chunk 1: bytes 0 - (CHUNK-1) / total
    r1 = chunk_route.calls[0].request
    assert r1.headers["Content-Range"] == f"bytes 0-{_CHUNK_SIZE - 1}/{total}"
    assert r1.headers["Content-Length"] == str(_CHUNK_SIZE)
    assert "Authorization" not in r1.headers  # uploadUrl is pre-signed

    # Chunk 2: bytes CHUNK - 2*CHUNK-1
    r2 = chunk_route.calls[1].request
    assert r2.headers["Content-Range"] == (
        f"bytes {_CHUNK_SIZE}-{2 * _CHUNK_SIZE - 1}/{total}"
    )

    # Chunk 3: final trailing bytes
    r3 = chunk_route.calls[2].request
    assert r3.headers["Content-Range"] == (
        f"bytes {2 * _CHUNK_SIZE}-{total - 1}/{total}"
    )
    assert r3.headers["Content-Length"] == "17"

    out = results[0][0].json
    assert out["status"] == 201
    assert out["response"]["id"] == "big-id"


@respx.mock
async def test_upload_large_errors_when_session_missing_upload_url() -> None:
    respx.post(
        f"{_GRAPH}/root:/x.bin:/createUploadSession",
    ).mock(return_value=Response(200, json={}))
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={
            "operation": "upload_large",
            "file_path": "x.bin",
            "content_base64": base64.b64encode(b"hello").decode("ascii"),
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="uploadUrl"):
        await OneDriveNode().execute(_ctx_for(node), [Item()])


async def test_upload_large_rejects_misaligned_chunk_size() -> None:
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={
            "operation": "upload_large",
            "file_path": "x.bin",
            "content_base64": base64.b64encode(b"hi").decode("ascii"),
            "chunk_size_bytes": 1000,  # not a multiple of 320 KiB
        },
        credentials={"microsoft_graph": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="320 KiB"):
        await OneDriveNode().execute(_ctx_for(node), [Item()])


# --- download_item -------------------------------------------------


@respx.mock
async def test_download_item_returns_base64_content() -> None:
    payload_bytes = b"one drive bytes"
    respx.get(f"{_GRAPH}/items/f1/content").mock(
        return_value=Response(
            200,
            content=payload_bytes,
            headers={"Content-Type": "text/plain"},
        ),
    )
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={"operation": "download_item", "item_id": "f1"},
        credentials={"microsoft_graph": _CRED_ID},
    )
    results = await OneDriveNode().execute(_ctx_for(node), [Item()])
    out = results[0][0].json
    assert out["response"]["content_base64"] == base64.b64encode(
        payload_bytes,
    ).decode("ascii")
    assert out["response"]["content_type"] == "text/plain"


# --- errors --------------------------------------------------------


@respx.mock
async def test_api_error_is_parsed() -> None:
    respx.get(f"{_GRAPH}/root/children").mock(
        return_value=Response(
            401, json={"error": {"message": "invalid token"}},
        ),
    )
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={"operation": "list_children"},
        credentials={"microsoft_graph": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid token"):
        await OneDriveNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="OneDrive",
        type="weftlyflow.onedrive",
        parameters={"operation": "list_children"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await OneDriveNode().execute(_ctx_for(node), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
