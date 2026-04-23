"""Unit tests for :class:`AscNode` and ``AscApiCredential``.

App Store Connect is the catalog's first ECDSA-signed (ES256) JWT
integration. Tests verify that (a) the credential mints a JWT whose
signature is a valid ECDSA signature of the signing input against the
configured public key, (b) the claims carry the expected iss/aud/exp
fields, and (c) each operation routes to the correct REST path.
"""

from __future__ import annotations

import base64
import json

import pytest
import respx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import AscApiCredential
from weftlyflow.credentials.types.asc_api import build_asc_token
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.asc import AscNode
from weftlyflow.nodes.integrations.asc.operations import build_request

_CRED_ID: str = "cr_asc"
_PROJECT_ID: str = "pr_test"
_ISSUER: str = "69a6de80-abcd-47e3-abcd-000000000000"
_KEY_ID: str = "ABC1234XYZ"
_API: str = "https://api.appstoreconnect.apple.com"


def _generate_p256_pem() -> tuple[str, ec.EllipticCurvePublicKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return pem, key.public_key()


_PEM, _PUBLIC_KEY = _generate_p256_pem()


def _resolver(
    *,
    issuer_id: str = _ISSUER,
    key_id: str = _KEY_ID,
    private_key: str = _PEM,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.asc_api": AscApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.asc_api",
                {
                    "issuer_id": issuer_id,
                    "key_id": key_id,
                    "private_key": private_key,
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


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _verify_es256(token: str, public_key: ec.EllipticCurvePublicKey) -> None:
    header_seg, claims_seg, sig_seg = token.split(".")
    raw_signature = _b64url_decode(sig_seg)
    component_size = len(raw_signature) // 2
    r = int.from_bytes(raw_signature[:component_size], "big")
    s = int.from_bytes(raw_signature[component_size:], "big")
    der_signature = utils.encode_dss_signature(r, s)
    signing_input = f"{header_seg}.{claims_seg}".encode("ascii")
    public_key.verify(der_signature, signing_input, ec.ECDSA(hashes.SHA256()))


# --- credential: token minting -----------------------------------


def test_build_token_produces_valid_es256_signature() -> None:
    token = build_asc_token(
        issuer_id=_ISSUER, key_id=_KEY_ID, private_key_pem=_PEM, now=1_700_000_000,
    )
    _verify_es256(token, _PUBLIC_KEY)


def test_token_header_declares_es256_and_kid() -> None:
    token = build_asc_token(
        issuer_id=_ISSUER, key_id=_KEY_ID, private_key_pem=_PEM, now=1_700_000_000,
    )
    header_seg, _, _ = token.split(".")
    header = json.loads(_b64url_decode(header_seg))
    assert header["alg"] == "ES256"
    assert header["kid"] == _KEY_ID
    assert header["typ"] == "JWT"


def test_token_claims_carry_iss_aud_and_expiry() -> None:
    now = 1_700_000_000
    token = build_asc_token(
        issuer_id=_ISSUER, key_id=_KEY_ID, private_key_pem=_PEM, now=now,
    )
    _, claims_seg, _ = token.split(".")
    claims = json.loads(_b64url_decode(claims_seg))
    assert claims["iss"] == _ISSUER
    assert claims["aud"] == "appstoreconnect-v1"
    assert claims["iat"] == now
    assert claims["exp"] == now + 1200


def test_build_token_rejects_non_pem_key() -> None:
    with pytest.raises(ValueError, match="valid PEM-encoded"):
        build_asc_token(
            issuer_id=_ISSUER, key_id=_KEY_ID, private_key_pem="not-a-key",
        )


def test_build_token_rejects_rsa_key() -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    with pytest.raises(ValueError, match="must be an EC"):
        build_asc_token(
            issuer_id=_ISSUER, key_id=_KEY_ID, private_key_pem=pem,
        )


def test_token_signature_verifies_against_tampered_input() -> None:
    token = build_asc_token(
        issuer_id=_ISSUER, key_id=_KEY_ID, private_key_pem=_PEM, now=1_700_000_000,
    )
    header_seg, claims_seg, sig_seg = token.split(".")
    tampered_signing_input = f"{header_seg}.{claims_seg}x".encode("ascii")
    raw_signature = _b64url_decode(sig_seg)
    r = int.from_bytes(raw_signature[:32], "big")
    s = int.from_bytes(raw_signature[32:], "big")
    der = utils.encode_dss_signature(r, s)
    with pytest.raises(InvalidSignature):
        _PUBLIC_KEY.verify(der, tampered_signing_input, ec.ECDSA(hashes.SHA256()))


# --- list_apps ---------------------------------------------------


@respx.mock
async def test_list_apps_sends_bearer_with_minted_jwt() -> None:
    route = respx.get(f"{_API}/v1/apps").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="ASC",
        type="weftlyflow.asc",
        parameters={"operation": "list_apps"},
        credentials={"asc_api": _CRED_ID},
    )
    await AscNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    assert sent.headers["Authorization"].startswith("Bearer ")
    token = sent.headers["Authorization"].removeprefix("Bearer ")
    _verify_es256(token, _PUBLIC_KEY)


@respx.mock
async def test_list_apps_forwards_limit_as_query_param() -> None:
    route = respx.get(f"{_API}/v1/apps", params={"limit": "25"}).mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="ASC",
        type="weftlyflow.asc",
        parameters={"operation": "list_apps", "limit": "25"},
        credentials={"asc_api": _CRED_ID},
    )
    await AscNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- get_app -----------------------------------------------------


@respx.mock
async def test_get_app_embeds_app_id_in_path() -> None:
    route = respx.get(f"{_API}/v1/apps/123456").mock(
        return_value=Response(200, json={"data": {"id": "123456"}}),
    )
    node = Node(
        id="node_1",
        name="ASC",
        type="weftlyflow.asc",
        parameters={"operation": "get_app", "app_id": "123456"},
        credentials={"asc_api": _CRED_ID},
    )
    await AscNode().execute(_ctx_for(node), [Item()])
    assert route.called


def test_get_app_requires_app_id() -> None:
    with pytest.raises(ValueError, match="'app_id' is required"):
        build_request("get_app", {})


# --- list_builds -------------------------------------------------


@respx.mock
async def test_list_builds_applies_app_filter() -> None:
    route = respx.get(
        f"{_API}/v1/builds", params={"filter[app]": "123456"},
    ).mock(return_value=Response(200, json={"data": []}))
    node = Node(
        id="node_1",
        name="ASC",
        type="weftlyflow.asc",
        parameters={"operation": "list_builds", "app_id": "123456"},
        credentials={"asc_api": _CRED_ID},
    )
    await AscNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- list_beta_testers -------------------------------------------


@respx.mock
async def test_list_beta_testers_hits_beta_endpoint() -> None:
    route = respx.get(f"{_API}/v1/betaTesters").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="ASC",
        type="weftlyflow.asc",
        parameters={"operation": "list_beta_testers"},
        credentials={"asc_api": _CRED_ID},
    )
    await AscNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- validation --------------------------------------------------


def test_limit_rejects_non_integer() -> None:
    with pytest.raises(ValueError, match="'limit' must be an integer"):
        build_request("list_apps", {"limit": "abc"})


def test_limit_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="'limit' must be between"):
        build_request("list_apps", {"limit": "500"})


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})


# --- errors ------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_errors_detail() -> None:
    respx.get(f"{_API}/v1/apps").mock(
        return_value=Response(
            401,
            json={"errors": [{"code": "NOT_AUTHORIZED", "detail": "Bad JWT"}]},
        ),
    )
    node = Node(
        id="node_1",
        name="ASC",
        type="weftlyflow.asc",
        parameters={"operation": "list_apps"},
        credentials={"asc_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="Bad JWT"):
        await AscNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="ASC",
        type="weftlyflow.asc",
        parameters={"operation": "list_apps"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await AscNode().execute(_ctx_for(node), [Item()])


async def test_empty_issuer_raises() -> None:
    resolver = _resolver(issuer_id="")
    node = Node(
        id="node_1",
        name="ASC",
        type="weftlyflow.asc",
        parameters={"operation": "list_apps"},
        credentials={"asc_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'issuer_id'"):
        await AscNode().execute(_ctx_for(node, resolver=resolver), [Item()])
