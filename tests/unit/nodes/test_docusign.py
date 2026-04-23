"""Unit tests for :class:`DocuSignNode` and ``DocuSignJwtCredential``.

DocuSign is the catalog's first integration with a two-step auth
bootstrap: sign a short-lived RS256 JWT locally, then exchange it at
``/oauth/token`` for a Bearer. The tests verify that (a) the JWT's
header and claims are shaped the way DocuSign expects, (b) the
signature verifies under the matching RSA public key, and (c) the
node exchanges the JWT once and reuses the Bearer across each
operation.
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
from weftlyflow.credentials.types import DocuSignJwtCredential
from weftlyflow.credentials.types.docusign_jwt import (
    audience_for,
    build_jwt_assertion,
    oauth_host_for,
)
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.docusign import DocuSignNode
from weftlyflow.nodes.integrations.docusign.operations import build_request

_CRED_ID: str = "cr_docusign"
_PROJECT_ID: str = "pr_test"
_INTEGRATION_KEY: str = "int-key-uuid"
_USER_ID: str = "user-uuid"
_ACCOUNT_ID: str = "acc-uuid"
_ACCOUNT_BASE: str = "https://demo.docusign.net/restapi"
_OAUTH_DEMO: str = "https://account-d.docusign.com"
_OAUTH_LIVE: str = "https://account.docusign.com"
_ACCESS_TOKEN: str = "ds_access_token_abc123"


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
    integration_key: str = _INTEGRATION_KEY,
    user_id: str = _USER_ID,
    private_key: str = _PEM,
    environment: str = "demo",
    account_base_url: str = _ACCOUNT_BASE,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.docusign_jwt": DocuSignJwtCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.docusign_jwt",
                {
                    "integration_key": integration_key,
                    "user_id": user_id,
                    "private_key": private_key,
                    "environment": environment,
                    "account_base_url": account_base_url,
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
    padding_len = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding_len)


def _mock_oauth_ok(host: str = _OAUTH_DEMO) -> Any:
    return respx.post(f"{host}/oauth/token").mock(
        return_value=Response(200, json={"access_token": _ACCESS_TOKEN, "expires_in": 3600}),
    )


# --- credential: JWT shape ---------------------------------------


def test_build_jwt_header_is_rs256() -> None:
    jwt = build_jwt_assertion(
        integration_key=_INTEGRATION_KEY, user_id=_USER_ID,
        private_key_pem=_PEM, audience=audience_for("demo"),
        now=1_700_000_000,
    )
    header_seg, _, _ = jwt.split(".")
    assert json.loads(_b64url_decode(header_seg)) == {"alg": "RS256", "typ": "JWT"}


def test_build_jwt_claims_include_iss_sub_aud_scope() -> None:
    jwt = build_jwt_assertion(
        integration_key=_INTEGRATION_KEY, user_id=_USER_ID,
        private_key_pem=_PEM, audience=audience_for("demo"),
        now=1_700_000_000,
    )
    _, claims_seg, _ = jwt.split(".")
    claims = json.loads(_b64url_decode(claims_seg))
    assert claims["iss"] == _INTEGRATION_KEY
    assert claims["sub"] == _USER_ID
    assert claims["aud"] == "account-d.docusign.com"
    assert claims["scope"] == "signature impersonation"
    assert claims["iat"] == 1_700_000_000
    assert claims["exp"] == 1_700_000_000 + 3600


def test_jwt_signature_verifies_under_public_key() -> None:
    jwt = build_jwt_assertion(
        integration_key=_INTEGRATION_KEY, user_id=_USER_ID,
        private_key_pem=_PEM, audience=audience_for("demo"),
        now=1_700_000_000,
    )
    header_seg, claims_seg, sig_seg = jwt.split(".")
    signature = _b64url_decode(sig_seg)
    _PUBLIC_KEY.verify(
        signature, f"{header_seg}.{claims_seg}".encode("ascii"),
        padding.PKCS1v15(), hashes.SHA256(),
    )


def test_build_jwt_rejects_non_rsa_key() -> None:
    from cryptography.hazmat.primitives.asymmetric import ec
    ec_key = ec.generate_private_key(ec.SECP256R1())
    pem = ec_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    with pytest.raises(ValueError, match="must be an RSA"):
        build_jwt_assertion(
            integration_key=_INTEGRATION_KEY, user_id=_USER_ID,
            private_key_pem=pem, audience=audience_for("demo"),
        )


def test_oauth_host_routes_demo_and_live() -> None:
    assert oauth_host_for("demo") == _OAUTH_DEMO
    assert oauth_host_for("live") == _OAUTH_LIVE
    assert oauth_host_for(None) == _OAUTH_DEMO


def test_audience_flips_by_environment() -> None:
    assert audience_for("demo") == "account-d.docusign.com"
    assert audience_for("live") == "account.docusign.com"


# --- list_envelopes ----------------------------------------------


@respx.mock
async def test_list_envelopes_exchanges_jwt_then_calls_api() -> None:
    token_route = _mock_oauth_ok()
    api_route = respx.get(
        f"{_ACCOUNT_BASE}/v2.1/accounts/{_ACCOUNT_ID}/envelopes",
    ).mock(return_value=Response(200, json={"envelopes": []}))
    node = Node(
        id="node_1",
        name="DocuSign",
        type="weftlyflow.docusign",
        parameters={"operation": "list_envelopes", "account_id": _ACCOUNT_ID},
        credentials={"docusign_jwt": _CRED_ID},
    )
    await DocuSignNode().execute(_ctx_for(node), [Item()])
    assert token_route.called
    # Assertion passed to DocuSign must verify under the public key.
    form = parse_qs(token_route.calls.last.request.content.decode())
    assert form["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
    assertion = form["assertion"][0]
    header_seg, claims_seg, sig_seg = assertion.split(".")
    _PUBLIC_KEY.verify(
        _b64url_decode(sig_seg),
        f"{header_seg}.{claims_seg}".encode("ascii"),
        padding.PKCS1v15(), hashes.SHA256(),
    )
    # API request must carry the exchanged Bearer.
    assert api_route.calls.last.request.headers["Authorization"] == f"Bearer {_ACCESS_TOKEN}"


@respx.mock
async def test_list_envelopes_forwards_filter_params() -> None:
    _mock_oauth_ok()
    route = respx.get(
        f"{_ACCOUNT_BASE}/v2.1/accounts/{_ACCOUNT_ID}/envelopes",
        params={"from_date": "2025-01-01", "status": "sent"},
    ).mock(return_value=Response(200, json={}))
    node = Node(
        id="node_1",
        name="DocuSign",
        type="weftlyflow.docusign",
        parameters={
            "operation": "list_envelopes",
            "account_id": _ACCOUNT_ID,
            "from_date": "2025-01-01",
            "status": "sent",
        },
        credentials={"docusign_jwt": _CRED_ID},
    )
    await DocuSignNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- get_envelope ------------------------------------------------


@respx.mock
async def test_get_envelope_embeds_envelope_id() -> None:
    _mock_oauth_ok()
    route = respx.get(
        f"{_ACCOUNT_BASE}/v2.1/accounts/{_ACCOUNT_ID}/envelopes/env-1",
    ).mock(return_value=Response(200, json={"envelopeId": "env-1"}))
    node = Node(
        id="node_1",
        name="DocuSign",
        type="weftlyflow.docusign",
        parameters={
            "operation": "get_envelope",
            "account_id": _ACCOUNT_ID,
            "envelope_id": "env-1",
        },
        credentials={"docusign_jwt": _CRED_ID},
    )
    await DocuSignNode().execute(_ctx_for(node), [Item()])
    assert route.called


def test_get_envelope_requires_envelope_id() -> None:
    with pytest.raises(ValueError, match="'envelope_id' is required"):
        build_request("get_envelope", _ACCOUNT_ID, {})


# --- create_envelope ---------------------------------------------


@respx.mock
async def test_create_envelope_with_template_sends_template_roles() -> None:
    _mock_oauth_ok()
    route = respx.post(
        f"{_ACCOUNT_BASE}/v2.1/accounts/{_ACCOUNT_ID}/envelopes",
    ).mock(return_value=Response(200, json={"envelopeId": "env-2"}))
    roles = [{"email": "a@b.com", "name": "Alice", "roleName": "Signer"}]
    node = Node(
        id="node_1",
        name="DocuSign",
        type="weftlyflow.docusign",
        parameters={
            "operation": "create_envelope",
            "account_id": _ACCOUNT_ID,
            "email_subject": "Please sign",
            "template_id": "tpl-1",
            "template_roles": roles,
        },
        credentials={"docusign_jwt": _CRED_ID},
    )
    await DocuSignNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["emailSubject"] == "Please sign"
    assert body["status"] == "sent"
    assert body["templateId"] == "tpl-1"
    assert body["templateRoles"] == roles


def test_create_envelope_rejects_bad_status() -> None:
    with pytest.raises(ValueError, match="'status' must be one of"):
        build_request(
            "create_envelope",
            _ACCOUNT_ID,
            {
                "email_subject": "x",
                "template_id": "tpl",
                "template_roles": [{}],
                "status": "voided",
            },
        )


def test_create_envelope_requires_template_or_documents() -> None:
    with pytest.raises(ValueError, match="'template_id' or a non-empty"):
        build_request(
            "create_envelope",
            _ACCOUNT_ID,
            {"email_subject": "x"},
        )


# --- list_templates ----------------------------------------------


@respx.mock
async def test_list_templates_hits_templates_endpoint() -> None:
    _mock_oauth_ok()
    route = respx.get(
        f"{_ACCOUNT_BASE}/v2.1/accounts/{_ACCOUNT_ID}/templates",
    ).mock(return_value=Response(200, json={"envelopeTemplates": []}))
    node = Node(
        id="node_1",
        name="DocuSign",
        type="weftlyflow.docusign",
        parameters={"operation": "list_templates", "account_id": _ACCOUNT_ID},
        credentials={"docusign_jwt": _CRED_ID},
    )
    await DocuSignNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- errors ------------------------------------------------------


@respx.mock
async def test_oauth_exchange_failure_raises() -> None:
    respx.post(f"{_OAUTH_DEMO}/oauth/token").mock(
        return_value=Response(
            400, json={"error": "consent_required"},
        ),
    )
    node = Node(
        id="node_1",
        name="DocuSign",
        type="weftlyflow.docusign",
        parameters={"operation": "list_envelopes", "account_id": _ACCOUNT_ID},
        credentials={"docusign_jwt": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="failed to obtain access token"):
        await DocuSignNode().execute(_ctx_for(node), [Item()])


@respx.mock
async def test_api_error_surfaces_message() -> None:
    _mock_oauth_ok()
    respx.get(
        f"{_ACCOUNT_BASE}/v2.1/accounts/{_ACCOUNT_ID}/envelopes",
    ).mock(return_value=Response(403, json={"message": "insufficient permissions"}))
    node = Node(
        id="node_1",
        name="DocuSign",
        type="weftlyflow.docusign",
        parameters={"operation": "list_envelopes", "account_id": _ACCOUNT_ID},
        credentials={"docusign_jwt": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="insufficient permissions"):
        await DocuSignNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="DocuSign",
        type="weftlyflow.docusign",
        parameters={"operation": "list_envelopes", "account_id": _ACCOUNT_ID},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await DocuSignNode().execute(_ctx_for(node), [Item()])


async def test_empty_private_key_raises() -> None:
    resolver = _resolver(private_key="")
    node = Node(
        id="node_1",
        name="DocuSign",
        type="weftlyflow.docusign",
        parameters={"operation": "list_envelopes", "account_id": _ACCOUNT_ID},
        credentials={"docusign_jwt": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'private_key'"):
        await DocuSignNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_build_request_requires_account_id() -> None:
    with pytest.raises(ValueError, match="account_id is required"):
        build_request("list_envelopes", "", {})


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", _ACCOUNT_ID, {})
