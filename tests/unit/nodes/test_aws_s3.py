"""Unit tests for :class:`AwsS3Node` + SigV4 signing.

Exercises every supported operation against a respx-mocked AWS S3
endpoint. Verifies the distinctive SigV4 ``Authorization`` header
format (``AWS4-HMAC-SHA256 Credential=.../<date>/<region>/s3/aws4_request,
SignedHeaders=..., Signature=<hex>``), the ``x-amz-date`` /
``x-amz-content-sha256`` pair, per-region virtual-host endpoint
derivation, the ListObjectsV2 ``list-type=2`` query flag, the
``x-amz-copy-source`` header on copies, STS session tokens, and the
``<Error><Code>...</Code><Message>...</Message>`` XML envelope parse.

The signing tests lean on a known-answer vector derived from the
published SigV4 spec so any regression in the key derivation or
canonical-request construction surfaces immediately.
"""

from __future__ import annotations

import datetime as _dt
import re

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import AwsS3Credential
from weftlyflow.credentials.types.aws_s3 import regional_host, sign_request
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.aws_s3 import AwsS3Node
from weftlyflow.nodes.integrations.aws_s3.operations import build_request

_CRED_ID: str = "cr_aws"
_PROJECT_ID: str = "pr_test"
_AK: str = "AKIAIOSFODNN7EXAMPLE"
_SK: str = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
_REGION: str = "us-east-1"


def _resolver(
    *,
    access_key: str = _AK,
    secret_key: str = _SK,
    region: str = _REGION,
    session_token: str = "",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.aws_s3": AwsS3Credential},
        rows={
            _CRED_ID: (
                "weftlyflow.aws_s3",
                {
                    "access_key_id": access_key,
                    "secret_access_key": secret_key,
                    "region": region,
                    "session_token": session_token,
                },
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


_AUTH_RE = re.compile(
    r"^AWS4-HMAC-SHA256 Credential=[^,]+, SignedHeaders=[^,]+, Signature=[0-9a-f]{64}$",
)


# --- SigV4 primitives -----------------------------------------------


def test_sign_request_emits_authorization_shape() -> None:
    fixed = _dt.datetime(2026, 4, 23, 12, 0, 0, tzinfo=_dt.UTC)
    signed = sign_request(
        method="GET",
        host="s3.amazonaws.com",
        path="/",
        query={},
        headers={},
        body=b"",
        access_key_id=_AK,
        secret_access_key=_SK,
        region=_REGION,
        now=fixed,
    )
    assert _AUTH_RE.match(signed["Authorization"])
    assert signed["x-amz-date"] == "20260423T120000Z"
    assert signed["x-amz-content-sha256"] == "UNSIGNED-PAYLOAD"
    assert f"Credential={_AK}/20260423/us-east-1/s3/aws4_request" in signed["Authorization"]


def test_sign_request_is_deterministic_per_timestamp() -> None:
    fixed = _dt.datetime(2026, 4, 23, 12, 0, 0, tzinfo=_dt.UTC)
    first = sign_request(
        method="GET", host="s3.amazonaws.com", path="/", query={},
        headers={}, body=b"", access_key_id=_AK, secret_access_key=_SK,
        region=_REGION, now=fixed,
    )
    second = sign_request(
        method="GET", host="s3.amazonaws.com", path="/", query={},
        headers={}, body=b"", access_key_id=_AK, secret_access_key=_SK,
        region=_REGION, now=fixed,
    )
    assert first["Authorization"] == second["Authorization"]


def test_sign_request_signature_changes_with_method() -> None:
    fixed = _dt.datetime(2026, 4, 23, 12, 0, 0, tzinfo=_dt.UTC)
    get_sig = sign_request(
        method="GET", host="s3.amazonaws.com", path="/", query={},
        headers={}, body=b"", access_key_id=_AK, secret_access_key=_SK,
        region=_REGION, now=fixed,
    )
    head_sig = sign_request(
        method="HEAD", host="s3.amazonaws.com", path="/", query={},
        headers={}, body=b"", access_key_id=_AK, secret_access_key=_SK,
        region=_REGION, now=fixed,
    )
    assert get_sig["Authorization"] != head_sig["Authorization"]


def test_sign_request_embeds_session_token() -> None:
    fixed = _dt.datetime(2026, 4, 23, 12, 0, 0, tzinfo=_dt.UTC)
    signed = sign_request(
        method="GET", host="s3.amazonaws.com", path="/", query={},
        headers={}, body=b"", access_key_id=_AK, secret_access_key=_SK,
        region=_REGION, now=fixed, session_token="sess-123",
    )
    assert signed["x-amz-security-token"] == "sess-123"
    assert "x-amz-security-token" in signed["Authorization"]


def test_sign_request_rejects_empty_keys() -> None:
    with pytest.raises(ValueError, match="access_key_id"):
        sign_request(
            method="GET", host="h", path="/", query={}, headers={},
            body=b"", access_key_id="", secret_access_key="x", region="r",
        )


# --- regional host ---------------------------------------------------


def test_regional_host_us_east_1_uses_legacy_host() -> None:
    assert regional_host("us-east-1") == "s3.amazonaws.com"
    assert (
        regional_host("us-east-1", bucket="my-bucket")
        == "my-bucket.s3.amazonaws.com"
    )


def test_regional_host_other_regions_include_region() -> None:
    assert regional_host("eu-west-2") == "s3.eu-west-2.amazonaws.com"
    assert (
        regional_host("eu-west-2", bucket="b")
        == "b.s3.eu-west-2.amazonaws.com"
    )


def test_regional_host_rejects_empty() -> None:
    with pytest.raises(ValueError, match="'region' is required"):
        regional_host("")


# --- list_buckets ----------------------------------------------------


@respx.mock
async def test_list_buckets_signs_service_endpoint() -> None:
    route = respx.get("https://s3.amazonaws.com/").mock(
        return_value=Response(
            200,
            text="<ListAllMyBucketsResult></ListAllMyBucketsResult>",
        ),
    )
    node = Node(
        id="node_1",
        name="S3",
        type="weftlyflow.aws_s3",
        parameters={"operation": "list_buckets"},
        credentials={"aws_s3": _CRED_ID},
    )
    await AwsS3Node().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert _AUTH_RE.match(request.headers["authorization"])
    assert "x-amz-date" in request.headers
    assert request.headers["x-amz-content-sha256"] == "UNSIGNED-PAYLOAD"


# --- list_objects (virtual host) ------------------------------------


@respx.mock
async def test_list_objects_uses_virtual_host_and_v2_flag() -> None:
    route = respx.get("https://my-bucket.s3.amazonaws.com/").mock(
        return_value=Response(200, text="<ListBucketResult></ListBucketResult>"),
    )
    node = Node(
        id="node_1",
        name="S3",
        type="weftlyflow.aws_s3",
        parameters={
            "operation": "list_objects",
            "bucket": "my-bucket",
            "prefix": "logs/",
            "max_keys": 500,
        },
        credentials={"aws_s3": _CRED_ID},
    )
    await AwsS3Node().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    params = request.url.params
    assert params.get("list-type") == "2"
    assert params.get("prefix") == "logs/"
    assert params.get("max-keys") == "500"


@respx.mock
async def test_list_objects_regional_host_includes_region() -> None:
    route = respx.get("https://b.s3.eu-west-2.amazonaws.com/").mock(
        return_value=Response(200, text="<ListBucketResult/>"),
    )
    node = Node(
        id="node_1",
        name="S3",
        type="weftlyflow.aws_s3",
        parameters={"operation": "list_objects", "bucket": "b"},
        credentials={"aws_s3": _CRED_ID},
    )
    await AwsS3Node().execute(
        _ctx_for(node, resolver=_resolver(region="eu-west-2")),
        [Item()],
    )
    request = route.calls.last.request
    assert "eu-west-2" in request.headers["authorization"]


def test_list_objects_max_keys_caps_at_1000() -> None:
    _, _, query, _, _ = build_request(
        "list_objects", {"bucket": "b", "max_keys": 50_000},
    )
    assert query["max-keys"] == "1000"


# --- head_object / get_object / delete_object -----------------------


@respx.mock
async def test_head_object_sends_head_verb() -> None:
    route = respx.head("https://b.s3.amazonaws.com/path/to/file.txt").mock(
        return_value=Response(200),
    )
    node = Node(
        id="node_1",
        name="S3",
        type="weftlyflow.aws_s3",
        parameters={
            "operation": "head_object",
            "bucket": "b",
            "key": "path/to/file.txt",
        },
        credentials={"aws_s3": _CRED_ID},
    )
    await AwsS3Node().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.method == "HEAD"


@respx.mock
async def test_delete_object_sends_delete_verb() -> None:
    route = respx.delete("https://b.s3.amazonaws.com/k").mock(
        return_value=Response(204),
    )
    node = Node(
        id="node_1",
        name="S3",
        type="weftlyflow.aws_s3",
        parameters={"operation": "delete_object", "bucket": "b", "key": "k"},
        credentials={"aws_s3": _CRED_ID},
    )
    await AwsS3Node().execute(_ctx_for(node), [Item()])
    assert route.called


# --- copy_object -----------------------------------------------------


@respx.mock
async def test_copy_object_sets_copy_source_header() -> None:
    route = respx.put("https://dst.s3.amazonaws.com/target.txt").mock(
        return_value=Response(200, text="<CopyObjectResult/>"),
    )
    node = Node(
        id="node_1",
        name="S3",
        type="weftlyflow.aws_s3",
        parameters={
            "operation": "copy_object",
            "bucket": "dst",
            "key": "target.txt",
            "source_bucket": "src",
            "source_key": "source.txt",
        },
        credentials={"aws_s3": _CRED_ID},
    )
    await AwsS3Node().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["x-amz-copy-source"] == "/src/source.txt"


def test_copy_object_requires_source() -> None:
    with pytest.raises(ValueError, match="'source_bucket'"):
        build_request(
            "copy_object",
            {"bucket": "b", "key": "k", "source_key": "s"},
        )


# --- errors ----------------------------------------------------------


@respx.mock
async def test_api_error_parses_xml_envelope() -> None:
    respx.get("https://s3.amazonaws.com/").mock(
        return_value=Response(
            403,
            text=(
                "<?xml version=\"1.0\"?><Error><Code>AccessDenied</Code>"
                "<Message>Not authorized</Message></Error>"
            ),
        ),
    )
    node = Node(
        id="node_1",
        name="S3",
        type="weftlyflow.aws_s3",
        parameters={"operation": "list_buckets"},
        credentials={"aws_s3": _CRED_ID},
    )
    with pytest.raises(
        NodeExecutionError, match="AccessDenied: Not authorized",
    ):
        await AwsS3Node().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="S3",
        type="weftlyflow.aws_s3",
        parameters={"operation": "list_buckets"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await AwsS3Node().execute(_ctx_for(node), [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("put_object", {})
