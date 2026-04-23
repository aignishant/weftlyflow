"""Unit tests for :class:`BackblazeB2Node` + :class:`BackblazeB2Credential`.

Backblaze B2's Native API is the first integration in the catalog
that requires an *authorize-and-discover* hop before any other call.
``b2_authorize_account`` returns both the session ``authorizationToken``
and a tenant-specific ``apiUrl`` — the node must honor both. These
tests pin that flow, verify the session is exchanged exactly once,
and check that each supported operation posts the documented path
and JSON body against the returned ``apiUrl``.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import BackblazeB2Credential
from weftlyflow.credentials.types.backblaze_b2 import (
    authorize_host,
    basic_auth_header,
)
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.backblaze_b2 import BackblazeB2Node
from weftlyflow.nodes.integrations.backblaze_b2.operations import build_request

_CRED_ID: str = "cr_b2"
_PROJECT_ID: str = "pr_test"
_KEY_ID: str = "0025fff000000000000000001"
_APP_KEY: str = "K002abc123def456ghi789jkl012mno345"
_AUTHORIZE_URL: str = f"{authorize_host()}/b2api/v3/b2_authorize_account"
_API_URL: str = "https://api001.backblazeb2.com"
_DOWNLOAD_URL: str = "https://f001.backblazeb2.com"
_ACCOUNT_ID: str = "acct-demo"
_TOKEN: str = "4_0025fff_session_token"


def _authorize_body() -> dict[str, Any]:
    return {
        "accountId": _ACCOUNT_ID,
        "authorizationToken": _TOKEN,
        "apiInfo": {
            "storageApi": {
                "apiUrl": _API_URL,
                "downloadUrl": _DOWNLOAD_URL,
                "absoluteMinimumPartSize": 5_000_000,
                "recommendedPartSize": 100_000_000,
            },
        },
    }


def _resolver(
    *,
    key_id: str = _KEY_ID,
    application_key: str = _APP_KEY,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.backblaze_b2": BackblazeB2Credential},
        rows={
            _CRED_ID: (
                "weftlyflow.backblaze_b2",
                {"key_id": key_id, "application_key": application_key},
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


def _mock_authorize_ok() -> respx.Route:
    return respx.get(_AUTHORIZE_URL).mock(
        return_value=Response(200, json=_authorize_body()),
    )


# --- authorize -----------------------------------------------------------


def test_basic_auth_header_round_trip() -> None:
    header = basic_auth_header(_KEY_ID, _APP_KEY)
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header.removeprefix("Basic ")).decode("ascii")
    assert decoded == f"{_KEY_ID}:{_APP_KEY}"


@respx.mock
async def test_authorize_uses_basic_auth_header() -> None:
    route = _mock_authorize_ok()
    node = Node(
        id="node_1",
        name="B2",
        type="weftlyflow.backblaze_b2",
        parameters={"operation": "list_buckets"},
        credentials={"backblaze_b2": _CRED_ID},
    )
    respx.post(f"{_API_URL}/b2api/v3/b2_list_buckets").mock(
        return_value=Response(200, json={"buckets": []}),
    )
    await BackblazeB2Node().execute(_ctx_for(node), [Item()])
    authz = route.calls.last.request.headers["authorization"]
    assert authz == basic_auth_header(_KEY_ID, _APP_KEY)


@respx.mock
async def test_authorize_called_once_across_items() -> None:
    auth_route = _mock_authorize_ok()
    list_route = respx.post(f"{_API_URL}/b2api/v3/b2_list_buckets").mock(
        return_value=Response(200, json={"buckets": []}),
    )
    node = Node(
        id="node_1",
        name="B2",
        type="weftlyflow.backblaze_b2",
        parameters={"operation": "list_buckets"},
        credentials={"backblaze_b2": _CRED_ID},
    )
    await BackblazeB2Node().execute(
        _ctx_for(node), [Item(), Item(), Item()],
    )
    assert auth_route.call_count == 1
    assert list_route.call_count == 3


@respx.mock
async def test_authorize_rejection_raises() -> None:
    respx.get(_AUTHORIZE_URL).mock(
        return_value=Response(401, json={"message": "invalid"}),
    )
    node = Node(
        id="node_1",
        name="B2",
        type="weftlyflow.backblaze_b2",
        parameters={"operation": "list_buckets"},
        credentials={"backblaze_b2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="authorize failed"):
        await BackblazeB2Node().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_authorize_missing_api_url_raises() -> None:
    respx.get(_AUTHORIZE_URL).mock(
        return_value=Response(
            200,
            json={
                "accountId": _ACCOUNT_ID,
                "authorizationToken": _TOKEN,
                "apiInfo": {"storageApi": {}},
            },
        ),
    )
    node = Node(
        id="node_1",
        name="B2",
        type="weftlyflow.backblaze_b2",
        parameters={"operation": "list_buckets"},
        credentials={"backblaze_b2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="missing required fields"):
        await BackblazeB2Node().execute(_ctx_for(node), [Item()])


# --- operations ---------------------------------------------------------


@respx.mock
async def test_list_buckets_injects_account_id() -> None:
    _mock_authorize_ok()
    route = respx.post(f"{_API_URL}/b2api/v3/b2_list_buckets").mock(
        return_value=Response(200, json={"buckets": []}),
    )
    node = Node(
        id="node_1",
        name="B2",
        type="weftlyflow.backblaze_b2",
        parameters={"operation": "list_buckets"},
        credentials={"backblaze_b2": _CRED_ID},
    )
    await BackblazeB2Node().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["authorization"] == _TOKEN
    body = request.read()
    assert b'"accountId"' in body
    assert _ACCOUNT_ID.encode() in body


@respx.mock
async def test_list_file_names_passes_paging_body() -> None:
    _mock_authorize_ok()
    route = respx.post(f"{_API_URL}/b2api/v3/b2_list_file_names").mock(
        return_value=Response(200, json={"files": [], "nextFileName": None}),
    )
    node = Node(
        id="node_1",
        name="B2",
        type="weftlyflow.backblaze_b2",
        parameters={
            "operation": "list_file_names",
            "bucket_id": "buck-1",
            "prefix": "logs/",
            "max_file_count": 250,
        },
        credentials={"backblaze_b2": _CRED_ID},
    )
    await BackblazeB2Node().execute(_ctx_for(node), [Item()])
    body = route.calls.last.request.read()
    assert b'"bucketId":"buck-1"' in body
    assert b'"prefix":"logs/"' in body
    assert b'"maxFileCount":250' in body


@respx.mock
async def test_get_upload_url_posts_bucket_id() -> None:
    _mock_authorize_ok()
    route = respx.post(f"{_API_URL}/b2api/v3/b2_get_upload_url").mock(
        return_value=Response(
            200,
            json={"uploadUrl": "https://pod.b2.com/upload", "authorizationToken": "u"},
        ),
    )
    node = Node(
        id="node_1",
        name="B2",
        type="weftlyflow.backblaze_b2",
        parameters={"operation": "get_upload_url", "bucket_id": "buck-1"},
        credentials={"backblaze_b2": _CRED_ID},
    )
    await BackblazeB2Node().execute(_ctx_for(node), [Item()])
    assert route.called


@respx.mock
async def test_delete_file_version_requires_file_id_and_name() -> None:
    _mock_authorize_ok()
    route = respx.post(f"{_API_URL}/b2api/v3/b2_delete_file_version").mock(
        return_value=Response(200, json={"fileId": "f1", "fileName": "a.txt"}),
    )
    node = Node(
        id="node_1",
        name="B2",
        type="weftlyflow.backblaze_b2",
        parameters={
            "operation": "delete_file_version",
            "file_id": "f1",
            "file_name": "a.txt",
        },
        credentials={"backblaze_b2": _CRED_ID},
    )
    await BackblazeB2Node().execute(_ctx_for(node), [Item()])
    body = route.calls.last.request.read()
    assert b'"fileId":"f1"' in body
    assert b'"fileName":"a.txt"' in body


# --- errors --------------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_message_field() -> None:
    _mock_authorize_ok()
    respx.post(f"{_API_URL}/b2api/v3/b2_list_file_names").mock(
        return_value=Response(
            400,
            json={"status": 400, "code": "bad_request", "message": "missing bucketId"},
        ),
    )
    node = Node(
        id="node_1",
        name="B2",
        type="weftlyflow.backblaze_b2",
        parameters={"operation": "list_file_names", "bucket_id": "b"},
        credentials={"backblaze_b2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="missing bucketId"):
        await BackblazeB2Node().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="B2",
        type="weftlyflow.backblaze_b2",
        parameters={"operation": "list_buckets"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await BackblazeB2Node().execute(_ctx_for(node), [Item()])


async def test_empty_application_key_raises() -> None:
    node = Node(
        id="node_1",
        name="B2",
        type="weftlyflow.backblaze_b2",
        parameters={"operation": "list_buckets"},
        credentials={"backblaze_b2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="'application_key'"):
        await BackblazeB2Node().execute(
            _ctx_for(node, resolver=_resolver(application_key="")),
            [Item()],
        )


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("copy_file", {})


def test_list_file_names_caps_max_file_count() -> None:
    _, body = build_request(
        "list_file_names",
        {"bucket_id": "b", "max_file_count": 99_999},
    )
    assert body["maxFileCount"] == 10_000


def test_list_file_names_rejects_invalid_max() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        build_request(
            "list_file_names",
            {"bucket_id": "b", "max_file_count": "abc"},
        )


def test_delete_file_version_requires_file_id() -> None:
    with pytest.raises(ValueError, match="'file_id'"):
        build_request("delete_file_version", {"file_name": "x"})
