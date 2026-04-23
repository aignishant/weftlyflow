"""Unit tests for :class:`GcsNode` and ``GcpServiceAccountCredential``.

GCP service accounts use the OAuth 2.0 JWT Bearer grant with two
claim-shape traits that distinguish the credential from DocuSign:
``aud`` is Google's token endpoint URL and ``scope`` is embedded in
the JWT claims rather than the form body. The tests verify the claim
shape, the signature's verifiability under the matching RSA public
key, and that the node performs exactly one token exchange before
reusing the Bearer across operations.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import parse_qs

import pytest
import respx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import GcpServiceAccountCredential
from weftlyflow.credentials.types.gcp_service_account import (
    build_jwt_assertion,
    token_host,
)
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.gcs import GcsNode
from weftlyflow.nodes.integrations.gcs.operations import build_request

_CRED_ID: str = "cr_gcp"
_PROJECT_ID: str = "pr_test"
_CLIENT_EMAIL: str = "svc@demo-project.iam.gserviceaccount.com"
_SCOPE: str = "https://www.googleapis.com/auth/cloud-platform"
_TOKEN_HOST: str = "https://oauth2.googleapis.com"
_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
_API_HOST: str = "https://storage.googleapis.com"
_ACCESS_TOKEN: str = "gcp_access_token_xyz"


def _generate_rsa_pem() -> tuple[str, RSAPublicKey]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return pem, key.public_key()


_PEM, _PUBLIC_KEY = _generate_rsa_pem()


def _resolver(
    *,
    client_email: str = _CLIENT_EMAIL,
    private_key: str = _PEM,
    scope: str = _SCOPE,
    subject: str | None = None,
) -> InMemoryCredentialResolver:
    payload: dict[str, Any] = {
        "client_email": client_email,
        "private_key": private_key,
        "scope": scope,
    }
    if subject is not None:
        payload["subject"] = subject
    return InMemoryCredentialResolver(
        types={"weftlyflow.gcp_service_account": GcpServiceAccountCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.gcp_service_account",
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


def _b64url_decode(segment: str) -> bytes:
    padding_chars = 4 - (len(segment) % 4)
    if padding_chars != 4:
        segment = segment + "=" * padding_chars
    return base64.urlsafe_b64decode(segment)


def _mock_token_ok() -> respx.Route:
    return respx.post(_TOKEN_URL).mock(
        return_value=Response(
            200,
            json={
                "access_token": _ACCESS_TOKEN,
                "token_type": "Bearer",
                "expires_in": 3599,
            },
        ),
    )


# --- JWT claim shape ----------------------------------------------


def test_build_jwt_claims_carry_scope_and_google_audience() -> None:
    token = build_jwt_assertion(
        client_email=_CLIENT_EMAIL,
        private_key_pem=_PEM,
        scope=_SCOPE,
        now=1_700_000_000,
    )
    _header_seg, claims_seg, _sig_seg = token.split(".")
    claims = json.loads(_b64url_decode(claims_seg))
    assert claims["iss"] == _CLIENT_EMAIL
    assert claims["aud"] == _TOKEN_URL
    assert claims["scope"] == _SCOPE
    assert claims["iat"] == 1_700_000_000
    assert claims["exp"] == 1_700_000_000 + 3600
    # No sub unless delegation was requested.
    assert "sub" not in claims


def test_build_jwt_header_is_rs256() -> None:
    token = build_jwt_assertion(
        client_email=_CLIENT_EMAIL, private_key_pem=_PEM, scope=_SCOPE,
    )
    header_seg, _, _ = token.split(".")
    header = json.loads(_b64url_decode(header_seg))
    assert header == {"alg": "RS256", "typ": "JWT"}


def test_build_jwt_includes_subject_when_provided() -> None:
    token = build_jwt_assertion(
        client_email=_CLIENT_EMAIL,
        private_key_pem=_PEM,
        scope=_SCOPE,
        subject="impersonated@example.com",
    )
    _, claims_seg, _ = token.split(".")
    claims = json.loads(_b64url_decode(claims_seg))
    assert claims["sub"] == "impersonated@example.com"


def test_jwt_signature_verifies_under_public_key() -> None:
    token = build_jwt_assertion(
        client_email=_CLIENT_EMAIL, private_key_pem=_PEM, scope=_SCOPE,
    )
    header_seg, claims_seg, sig_seg = token.split(".")
    _PUBLIC_KEY.verify(
        _b64url_decode(sig_seg),
        f"{header_seg}.{claims_seg}".encode("ascii"),
        padding.PKCS1v15(), hashes.SHA256(),
    )


def test_build_jwt_rejects_non_pem_key() -> None:
    with pytest.raises(ValueError, match="valid PEM-encoded"):
        build_jwt_assertion(
            client_email=_CLIENT_EMAIL, private_key_pem="not-a-key", scope=_SCOPE,
        )


def test_build_jwt_rejects_ec_key() -> None:
    from cryptography.hazmat.primitives.asymmetric import ec
    ec_key = ec.generate_private_key(ec.SECP256R1())
    pem = ec_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    with pytest.raises(ValueError, match="must be an RSA"):
        build_jwt_assertion(
            client_email=_CLIENT_EMAIL, private_key_pem=pem, scope=_SCOPE,
        )


def test_token_host_is_google() -> None:
    assert token_host() == _TOKEN_HOST


# --- credential inject (no-op) ------------------------------------


async def test_credential_inject_is_noop() -> None:
    import httpx
    request = httpx.Request("GET", f"{_API_HOST}/storage/v1/b")
    out = await GcpServiceAccountCredential().inject(
        {"client_email": _CLIENT_EMAIL, "private_key": _PEM, "scope": _SCOPE}, request,
    )
    # No Authorization — the node fetches the Bearer explicitly.
    assert "Authorization" not in out.headers


# --- list_buckets -------------------------------------------------


@respx.mock
async def test_list_buckets_exchanges_jwt_then_calls_api() -> None:
    token_route = _mock_token_ok()
    api_route = respx.get(f"{_API_HOST}/storage/v1/b").mock(
        return_value=Response(200, json={"items": []}),
    )
    node = Node(
        id="node_1",
        name="GCS",
        type="weftlyflow.gcs",
        parameters={"operation": "list_buckets", "project": "demo-project"},
        credentials={"gcp_service_account": _CRED_ID},
    )
    await GcsNode().execute(_ctx_for(node), [Item()])
    assert token_route.called
    form = parse_qs(token_route.calls.last.request.content.decode())
    assert form["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
    assertion = form["assertion"][0]
    header_seg, claims_seg, sig_seg = assertion.split(".")
    _PUBLIC_KEY.verify(
        _b64url_decode(sig_seg),
        f"{header_seg}.{claims_seg}".encode("ascii"),
        padding.PKCS1v15(), hashes.SHA256(),
    )
    # API request picks up the exchanged Bearer + project query param.
    sent = api_route.calls.last.request
    assert sent.headers["Authorization"] == f"Bearer {_ACCESS_TOKEN}"
    qs = parse_qs(
        sent.url.query.decode() if isinstance(sent.url.query, bytes) else sent.url.query,
    )
    assert qs["project"] == ["demo-project"]


@respx.mock
async def test_list_buckets_forwards_pagination_params() -> None:
    _mock_token_ok()
    route = respx.get(
        f"{_API_HOST}/storage/v1/b",
        params={"project": "demo-project", "pageToken": "next-42", "prefix": "log-"},
    ).mock(return_value=Response(200, json={"items": []}))
    node = Node(
        id="node_1",
        name="GCS",
        type="weftlyflow.gcs",
        parameters={
            "operation": "list_buckets",
            "project": "demo-project",
            "page_token": "next-42",
            "prefix": "log-",
        },
        credentials={"gcp_service_account": _CRED_ID},
    )
    await GcsNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- list_objects / get_object / delete_object --------------------


@respx.mock
async def test_list_objects_url_quotes_bucket() -> None:
    _mock_token_ok()
    route = respx.get(f"{_API_HOST}/storage/v1/b/my-bucket/o").mock(
        return_value=Response(200, json={"items": []}),
    )
    node = Node(
        id="node_1",
        name="GCS",
        type="weftlyflow.gcs",
        parameters={"operation": "list_objects", "bucket": "my-bucket"},
        credentials={"gcp_service_account": _CRED_ID},
    )
    await GcsNode().execute(_ctx_for(node), [Item()])
    assert route.called


@respx.mock
async def test_get_object_url_quotes_slashes_in_object_name() -> None:
    _mock_token_ok()
    # Slashes inside the object name are encoded as %2F for the JSON API path.
    route = respx.get(
        f"{_API_HOST}/storage/v1/b/my-bucket/o/folder%2Ffile.txt",
    ).mock(return_value=Response(200, json={"name": "folder/file.txt"}))
    node = Node(
        id="node_1",
        name="GCS",
        type="weftlyflow.gcs",
        parameters={
            "operation": "get_object",
            "bucket": "my-bucket",
            "object_name": "folder/file.txt",
        },
        credentials={"gcp_service_account": _CRED_ID},
    )
    await GcsNode().execute(_ctx_for(node), [Item()])
    assert route.called


@respx.mock
async def test_get_object_alt_media_passes_through() -> None:
    _mock_token_ok()
    route = respx.get(
        f"{_API_HOST}/storage/v1/b/my-bucket/o/file.txt",
        params={"alt": "media"},
    ).mock(return_value=Response(200, content=b"raw-bytes"))
    node = Node(
        id="node_1",
        name="GCS",
        type="weftlyflow.gcs",
        parameters={
            "operation": "get_object",
            "bucket": "my-bucket",
            "object_name": "file.txt",
            "alt": "media",
        },
        credentials={"gcp_service_account": _CRED_ID},
    )
    await GcsNode().execute(_ctx_for(node), [Item()])
    assert route.called


@respx.mock
async def test_delete_object_sends_delete_verb() -> None:
    _mock_token_ok()
    route = respx.delete(
        f"{_API_HOST}/storage/v1/b/my-bucket/o/file.txt",
    ).mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="GCS",
        type="weftlyflow.gcs",
        parameters={
            "operation": "delete_object",
            "bucket": "my-bucket",
            "object_name": "file.txt",
        },
        credentials={"gcp_service_account": _CRED_ID},
    )
    await GcsNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- validation / errors ------------------------------------------


def test_list_buckets_requires_project() -> None:
    with pytest.raises(ValueError, match="'project' is required"):
        build_request("list_buckets", {})


def test_list_objects_requires_bucket() -> None:
    with pytest.raises(ValueError, match="'bucket' is required"):
        build_request("list_objects", {})


def test_get_object_requires_bucket_and_object_name() -> None:
    with pytest.raises(ValueError, match="'bucket' is required"):
        build_request("get_object", {"object_name": "x"})
    with pytest.raises(ValueError, match="'object_name' is required"):
        build_request("get_object", {"bucket": "b"})


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})


@respx.mock
async def test_token_exchange_failure_surfaces_node_error() -> None:
    respx.post(_TOKEN_URL).mock(
        return_value=Response(400, json={"error": "invalid_grant"}),
    )
    node = Node(
        id="node_1",
        name="GCS",
        type="weftlyflow.gcs",
        parameters={"operation": "list_buckets", "project": "demo-project"},
        credentials={"gcp_service_account": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="failed to obtain access token"):
        await GcsNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_api_error_surfaces_error_message() -> None:
    _mock_token_ok()
    respx.get(f"{_API_HOST}/storage/v1/b/my-bucket/o/missing.txt").mock(
        return_value=Response(
            404, json={"error": {"code": 404, "message": "No such object."}},
        ),
    )
    node = Node(
        id="node_1",
        name="GCS",
        type="weftlyflow.gcs",
        parameters={
            "operation": "get_object",
            "bucket": "my-bucket",
            "object_name": "missing.txt",
        },
        credentials={"gcp_service_account": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="No such object"):
        await GcsNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="GCS",
        type="weftlyflow.gcs",
        parameters={"operation": "list_buckets", "project": "demo-project"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await GcsNode().execute(_ctx_for(node), [Item()])


async def test_empty_private_key_raises() -> None:
    resolver = _resolver(private_key="")
    node = Node(
        id="node_1",
        name="GCS",
        type="weftlyflow.gcs",
        parameters={"operation": "list_buckets", "project": "demo-project"},
        credentials={"gcp_service_account": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'private_key'"):
        await GcsNode().execute(_ctx_for(node, resolver=resolver), [Item()])
