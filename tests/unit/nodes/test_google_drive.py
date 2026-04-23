"""Unit tests for :class:`GoogleDriveNode` and ``GoogleDriveOAuth2Credential``.

Exercises the distinctive ``multipart/related`` upload envelope — JSON
metadata + raw file bytes separated by a custom boundary — routed
through the ``/upload/drive/v3`` host variant, the
``application/vnd.google-apps.folder`` mime-type for folder creation,
the ``?alt=media`` download variant, and the Bearer-token credential
injection.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import GoogleDriveOAuth2Credential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.google_drive import GoogleDriveNode
from weftlyflow.nodes.integrations.google_drive.operations import build_request

_CRED_ID: str = "cr_gdrive"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "ya29.drive-test"
_API: str = "https://www.googleapis.com/drive/v3"
_UPLOAD: str = "https://www.googleapis.com/upload/drive/v3"


def _resolver(*, token: str = _TOKEN) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.google_drive_oauth2": GoogleDriveOAuth2Credential},
        rows={
            _CRED_ID: (
                "weftlyflow.google_drive_oauth2",
                {"access_token": token},
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


# --- credential ------------------------------------------------------


async def test_credential_inject_sets_bearer_token() -> None:
    request = httpx.Request("GET", f"{_API}/files")
    out = await GoogleDriveOAuth2Credential().inject(
        {"access_token": _TOKEN}, request,
    )
    assert out.headers["Authorization"] == f"Bearer {_TOKEN}"


def test_credential_has_drive_scope_default() -> None:
    props = {p.name: p for p in GoogleDriveOAuth2Credential.properties}
    assert "drive.file" in str(props["scope"].default)


# --- list_files -----------------------------------------------------


@respx.mock
async def test_list_files_forwards_query_params() -> None:
    route = respx.get(f"{_API}/files").mock(
        return_value=Response(200, json={"files": []}),
    )
    node = Node(
        id="node_1",
        name="Drive",
        type="weftlyflow.google_drive",
        parameters={
            "operation": "list_files",
            "q": "mimeType='application/pdf'",
            "pageSize": 5,
            "orderBy": "name",
        },
        credentials={"google_drive_oauth2": _CRED_ID},
    )
    await GoogleDriveNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params["q"] == "mimeType='application/pdf'"
    assert params["pageSize"] == "5"
    assert params["orderBy"] == "name"


# --- get_file -------------------------------------------------------


@respx.mock
async def test_get_file_percent_encodes_file_id() -> None:
    route = respx.get(f"{_API}/files/abc%2F123").mock(
        return_value=Response(200, json={"id": "abc/123"}),
    )
    node = Node(
        id="node_1",
        name="Drive",
        type="weftlyflow.google_drive",
        parameters={
            "operation": "get_file",
            "file_id": "abc/123",
            "fields": "id,name,parents",
        },
        credentials={"google_drive_oauth2": _CRED_ID},
    )
    await GoogleDriveNode().execute(_ctx_for(node), [Item()])
    assert route.called
    assert route.calls.last.request.url.params["fields"] == "id,name,parents"


# --- create_folder --------------------------------------------------


@respx.mock
async def test_create_folder_posts_folder_mime_type() -> None:
    route = respx.post(f"{_API}/files").mock(
        return_value=Response(200, json={"id": "f1"}),
    )
    node = Node(
        id="node_1",
        name="Drive",
        type="weftlyflow.google_drive",
        parameters={
            "operation": "create_folder",
            "name": "MyFolder",
            "parents": ["root"],
        },
        credentials={"google_drive_oauth2": _CRED_ID},
    )
    await GoogleDriveNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "name": "MyFolder",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": ["root"],
    }


# --- upload_file: multipart/related --------------------------------


@respx.mock
async def test_upload_file_sends_multipart_related_envelope() -> None:
    route = respx.post(f"{_UPLOAD}/files").mock(
        return_value=Response(200, json={"id": "u1"}),
    )
    content = b"hello drive"
    node = Node(
        id="node_1",
        name="Drive",
        type="weftlyflow.google_drive",
        parameters={
            "operation": "upload_file",
            "name": "hello.txt",
            "mime_type": "text/plain",
            "content_base64": base64.b64encode(content).decode("ascii"),
        },
        credentials={"google_drive_oauth2": _CRED_ID},
    )
    await GoogleDriveNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.url.params["uploadType"] == "multipart"
    content_type = request.headers["Content-Type"]
    assert content_type.startswith("multipart/related; boundary=")
    raw = request.content
    assert b'Content-Type: application/json; charset=UTF-8' in raw
    assert b'"name":"hello.txt"' in raw
    assert b"Content-Type: text/plain" in raw
    assert content in raw


def test_upload_file_rejects_invalid_base64() -> None:
    with pytest.raises(ValueError, match="not valid base64"):
        build_request(
            "upload_file",
            {"name": "x", "content_base64": "this is not base64!"},
        )


def test_upload_file_requires_name() -> None:
    with pytest.raises(ValueError, match="'name' is required"):
        build_request(
            "upload_file", {"content_base64": base64.b64encode(b"x").decode()},
        )


# --- download_file --------------------------------------------------


@respx.mock
async def test_download_file_returns_base64_content() -> None:
    payload_bytes = b"the quick brown fox"
    respx.get(f"{_API}/files/f1").mock(
        return_value=Response(
            200, content=payload_bytes,
            headers={"Content-Type": "application/octet-stream"},
        ),
    )
    node = Node(
        id="node_1",
        name="Drive",
        type="weftlyflow.google_drive",
        parameters={"operation": "download_file", "file_id": "f1"},
        credentials={"google_drive_oauth2": _CRED_ID},
    )
    results = await GoogleDriveNode().execute(_ctx_for(node), [Item()])
    out = results[0][0].json
    assert out["response"]["content_base64"] == base64.b64encode(
        payload_bytes,
    ).decode("ascii")
    assert out["response"]["content_length"] == len(payload_bytes)


@respx.mock
async def test_download_file_adds_alt_media_query() -> None:
    route = respx.get(f"{_API}/files/f1").mock(return_value=Response(200, content=b""))
    node = Node(
        id="node_1",
        name="Drive",
        type="weftlyflow.google_drive",
        parameters={"operation": "download_file", "file_id": "f1"},
        credentials={"google_drive_oauth2": _CRED_ID},
    )
    await GoogleDriveNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.url.params["alt"] == "media"


# --- delete_file ---------------------------------------------------


@respx.mock
async def test_delete_file_issues_delete_verb() -> None:
    route = respx.delete(f"{_API}/files/f1").mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="Drive",
        type="weftlyflow.google_drive",
        parameters={"operation": "delete_file", "file_id": "f1"},
        credentials={"google_drive_oauth2": _CRED_ID},
    )
    await GoogleDriveNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- errors --------------------------------------------------------


@respx.mock
async def test_api_error_is_parsed() -> None:
    respx.get(f"{_API}/files").mock(
        return_value=Response(401, json={"error": {"message": "invalid creds"}}),
    )
    node = Node(
        id="node_1",
        name="Drive",
        type="weftlyflow.google_drive",
        parameters={"operation": "list_files"},
        credentials={"google_drive_oauth2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="invalid creds"):
        await GoogleDriveNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Drive",
        type="weftlyflow.google_drive",
        parameters={"operation": "list_files"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await GoogleDriveNode().execute(_ctx_for(node), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
