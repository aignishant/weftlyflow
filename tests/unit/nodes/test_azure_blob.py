"""Unit tests for :class:`AzureBlobNode` + SharedKey signing.

Azure Storage's SharedKey scheme is materially different from every
other HMAC-signing credential already in the catalog: the StringToSign
has a fixed 12-slot header prefix, the ``x-ms-*`` headers are
canonicalized separately, and the canonical resource merges the
account name with the URL path plus a sorted query block. These tests
pin that algorithm against a hand-computed reference vector, verify
each operation sends the expected method/path/query, and confirm the
``Authorization: SharedKey <account>:<b64sig>`` header format.
"""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import re
from typing import Any

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import AzureStorageSharedKeyCredential
from weftlyflow.credentials.types.azure_storage_shared_key import (
    authorize_request,
    blob_host_for,
    build_string_to_sign,
    sign_string,
)
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.azure_blob import AzureBlobNode
from weftlyflow.nodes.integrations.azure_blob.operations import build_request

_CRED_ID: str = "cr_azure"
_PROJECT_ID: str = "pr_test"
_ACCOUNT: str = "teststorage"
# 64-byte zero-bytes base64-encoded — valid shape for SharedKey, deterministic.
_ACCOUNT_KEY: str = base64.b64encode(b"\x00" * 64).decode("ascii")
_API_VERSION: str = "2023-11-03"
_AUTH_RE = re.compile(rf"^SharedKey {_ACCOUNT}:[A-Za-z0-9+/=]+$")


def _resolver(
    *,
    account_name: str = _ACCOUNT,
    account_key: str = _ACCOUNT_KEY,
    api_version: str = _API_VERSION,
) -> InMemoryCredentialResolver:
    payload: dict[str, Any] = {
        "account_name": account_name,
        "account_key": account_key,
        "api_version": api_version,
    }
    return InMemoryCredentialResolver(
        types={
            "weftlyflow.azure_storage_shared_key": AzureStorageSharedKeyCredential,
        },
        rows={
            _CRED_ID: (
                "weftlyflow.azure_storage_shared_key",
                payload,
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


def _reference_signature(string_to_sign: str, account_key: str) -> str:
    digest = hmac.new(
        base64.b64decode(account_key),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


# --- StringToSign primitives ---------------------------------------------


def test_build_string_to_sign_12_slot_prefix_on_empty_get() -> None:
    sts = build_string_to_sign(
        method="GET",
        account_name=_ACCOUNT,
        path="/",
        query="comp=list",
        headers={"x-ms-date": "Sat, 23 Apr 2026 12:00:00 GMT", "x-ms-version": _API_VERSION},
        content_length=0,
    )
    lines = sts.split("\n")
    # 1 verb + 11 standard header slots + blank 12th line after header block = specific shape
    assert lines[0] == "GET"
    # content-encoding..range are empty because only x-ms-* headers set
    assert lines[1:12] == ["", "", "", "", "", "", "", "", "", "", ""]
    assert "x-ms-date:Sat, 23 Apr 2026 12:00:00 GMT" in sts
    assert f"x-ms-version:{_API_VERSION}" in sts
    assert sts.rstrip().endswith(f"/{_ACCOUNT}/\ncomp:list")


def test_build_string_to_sign_emits_length_when_nonzero() -> None:
    sts = build_string_to_sign(
        method="PUT",
        account_name=_ACCOUNT,
        path="/c/b",
        query="",
        headers={
            "x-ms-date": "Sat, 23 Apr 2026 12:00:00 GMT",
            "x-ms-version": _API_VERSION,
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": "text/plain",
        },
        content_length=17,
    )
    lines = sts.split("\n")
    # Slot order: verb, enc, lang, length, md5, type, date, ifm, ifmat, ifnm, ifum, range
    assert lines[0] == "PUT"
    assert lines[3] == "17"
    assert lines[5] == "text/plain"


def test_build_string_to_sign_canonical_query_sorts_and_groups() -> None:
    sts = build_string_to_sign(
        method="GET",
        account_name=_ACCOUNT,
        path="/container",
        query="restype=container&comp=list&prefix=logs%2F",
        headers={"x-ms-date": "d", "x-ms-version": _API_VERSION},
        content_length=0,
    )
    tail = sts.split(f"/{_ACCOUNT}/container\n", 1)[1]
    # Keys lowercased, sorted alphabetically, values comma-joined and percent-decoded.
    assert tail.splitlines() == [
        "comp:list",
        "prefix:logs/",
        "restype:container",
    ]


def test_build_string_to_sign_groups_repeated_query_keys() -> None:
    sts = build_string_to_sign(
        method="GET",
        account_name=_ACCOUNT,
        path="/c",
        query="tag=b&tag=a",
        headers={},
        content_length=0,
    )
    assert sts.endswith("tag:a,b")


def test_sign_string_known_answer_matches_independent_hmac() -> None:
    sts = "GET\n\n\n\n\n\n\n\n\n\n\n\nx-ms-date:d\nx-ms-version:v\n/acct/"
    reference = _reference_signature(sts, _ACCOUNT_KEY)
    assert sign_string(sts, _ACCOUNT_KEY) == reference


def test_sign_string_rejects_non_base64_key() -> None:
    with pytest.raises(ValueError, match="base64"):
        sign_string("GET\n", "not-base64-!!")


# --- authorize_request ---------------------------------------------------


def test_authorize_request_stamps_headers_and_signs() -> None:
    fixed = _dt.datetime(2026, 4, 23, 12, 0, 0, tzinfo=_dt.UTC)
    request = httpx.Request(
        "GET", f"{blob_host_for(_ACCOUNT)}/?comp=list",
    )
    signed = authorize_request(
        request,
        account_name=_ACCOUNT,
        account_key=_ACCOUNT_KEY,
        api_version=_API_VERSION,
        now=fixed,
    )
    assert signed.headers["x-ms-date"] == "Thu, 23 Apr 2026 12:00:00 GMT"
    assert signed.headers["x-ms-version"] == _API_VERSION
    assert _AUTH_RE.match(signed.headers["Authorization"])


def test_authorize_request_signature_verifies_under_reference() -> None:
    fixed = _dt.datetime(2026, 4, 23, 12, 0, 0, tzinfo=_dt.UTC)
    request = httpx.Request("GET", f"{blob_host_for(_ACCOUNT)}/?comp=list")
    authorize_request(
        request,
        account_name=_ACCOUNT,
        account_key=_ACCOUNT_KEY,
        api_version=_API_VERSION,
        now=fixed,
    )
    expected_sts = build_string_to_sign(
        method="GET",
        account_name=_ACCOUNT,
        path="/",
        query="comp=list",
        headers=dict(request.headers),
        content_length=0,
    )
    expected_sig = _reference_signature(expected_sts, _ACCOUNT_KEY)
    assert request.headers["Authorization"] == f"SharedKey {_ACCOUNT}:{expected_sig}"


def test_authorize_request_preserves_caller_supplied_date() -> None:
    request = httpx.Request("GET", f"{blob_host_for(_ACCOUNT)}/?comp=list")
    request.headers["x-ms-date"] = "Sun, 01 Jan 2023 00:00:00 GMT"
    authorize_request(
        request,
        account_name=_ACCOUNT,
        account_key=_ACCOUNT_KEY,
        api_version=_API_VERSION,
    )
    assert request.headers["x-ms-date"] == "Sun, 01 Jan 2023 00:00:00 GMT"


# --- node dispatch -------------------------------------------------------


@respx.mock
async def test_list_containers_signs_service_endpoint() -> None:
    route = respx.get(f"{blob_host_for(_ACCOUNT)}/").mock(
        return_value=Response(
            200,
            text="<?xml version=\"1.0\"?><EnumerationResults/>",
        ),
    )
    node = Node(
        id="node_1",
        name="Azure",
        type="weftlyflow.azure_blob",
        parameters={"operation": "list_containers"},
        credentials={"azure_storage_shared_key": _CRED_ID},
    )
    await AzureBlobNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.url.params.get("comp") == "list"
    assert _AUTH_RE.match(request.headers["authorization"])
    assert "x-ms-date" in request.headers
    assert request.headers["x-ms-version"] == _API_VERSION


@respx.mock
async def test_list_blobs_adds_container_scope_flags() -> None:
    route = respx.get(f"{blob_host_for(_ACCOUNT)}/my-container").mock(
        return_value=Response(200, text="<EnumerationResults/>"),
    )
    node = Node(
        id="node_1",
        name="Azure",
        type="weftlyflow.azure_blob",
        parameters={
            "operation": "list_blobs",
            "container": "my-container",
            "prefix": "logs/",
            "delimiter": "/",
        },
        credentials={"azure_storage_shared_key": _CRED_ID},
    )
    await AzureBlobNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params.get("restype") == "container"
    assert params.get("comp") == "list"
    assert params.get("prefix") == "logs/"
    assert params.get("delimiter") == "/"


@respx.mock
async def test_get_blob_percent_encodes_folder_blob_names() -> None:
    route = respx.get(
        f"{blob_host_for(_ACCOUNT)}/c/folder%2Ffile.txt",
    ).mock(return_value=Response(200, content=b"payload"))
    node = Node(
        id="node_1",
        name="Azure",
        type="weftlyflow.azure_blob",
        parameters={
            "operation": "get_blob",
            "container": "c",
            "blob": "folder/file.txt",
        },
        credentials={"azure_storage_shared_key": _CRED_ID},
    )
    await AzureBlobNode().execute(_ctx_for(node), [Item()])
    assert route.called


@respx.mock
async def test_put_blob_sets_block_blob_headers_and_body() -> None:
    route = respx.put(f"{blob_host_for(_ACCOUNT)}/c/hello.txt").mock(
        return_value=Response(201),
    )
    node = Node(
        id="node_1",
        name="Azure",
        type="weftlyflow.azure_blob",
        parameters={
            "operation": "put_blob",
            "container": "c",
            "blob": "hello.txt",
            "body": "hello world",
            "content_type": "text/plain",
        },
        credentials={"azure_storage_shared_key": _CRED_ID},
    )
    await AzureBlobNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.method == "PUT"
    assert request.headers["x-ms-blob-type"] == "BlockBlob"
    assert request.headers["content-type"] == "text/plain"
    assert request.content == b"hello world"


@respx.mock
async def test_delete_blob_sends_delete_verb() -> None:
    route = respx.delete(f"{blob_host_for(_ACCOUNT)}/c/k").mock(
        return_value=Response(202),
    )
    node = Node(
        id="node_1",
        name="Azure",
        type="weftlyflow.azure_blob",
        parameters={"operation": "delete_blob", "container": "c", "blob": "k"},
        credentials={"azure_storage_shared_key": _CRED_ID},
    )
    await AzureBlobNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- errors --------------------------------------------------------------


@respx.mock
async def test_api_error_parses_azure_xml_envelope() -> None:
    respx.get(f"{blob_host_for(_ACCOUNT)}/c").mock(
        return_value=Response(
            403,
            text=(
                "<?xml version=\"1.0\"?><Error><Code>AuthenticationFailed</Code>"
                "<Message>Server failed to authenticate the request.</Message></Error>"
            ),
        ),
    )
    node = Node(
        id="node_1",
        name="Azure",
        type="weftlyflow.azure_blob",
        parameters={"operation": "list_blobs", "container": "c"},
        credentials={"azure_storage_shared_key": _CRED_ID},
    )
    with pytest.raises(
        NodeExecutionError,
        match="AuthenticationFailed: Server failed to authenticate the request",
    ):
        await AzureBlobNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Azure",
        type="weftlyflow.azure_blob",
        parameters={"operation": "list_containers"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await AzureBlobNode().execute(_ctx_for(node), [Item()])


async def test_empty_account_key_raises() -> None:
    node = Node(
        id="node_1",
        name="Azure",
        type="weftlyflow.azure_blob",
        parameters={"operation": "list_containers"},
        credentials={"azure_storage_shared_key": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="account_name or account_key"):
        await AzureBlobNode().execute(
            _ctx_for(node, resolver=_resolver(account_key="")),
            [Item()],
        )


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("upload_blob", {})


def test_put_blob_rejects_non_string_body() -> None:
    with pytest.raises(ValueError, match="'body'"):
        build_request(
            "put_blob",
            {"container": "c", "blob": "b", "body": 123},
        )


def test_blob_operation_requires_container() -> None:
    with pytest.raises(ValueError, match="'container'"):
        build_request("get_blob", {"blob": "b"})
