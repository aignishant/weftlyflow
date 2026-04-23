"""Unit tests for :class:`NetSuiteNode` and its OAuth 1.0a signer.

Exercises every supported operation against a respx-mocked SuiteTalk
REST API. Verifies the distinctive OAuth 1.0a HMAC-SHA256 Authorization
header (realm, nonce, timestamp, signature), the ``Prefer: transient``
SuiteQL header, record-path dispatch (GET/POST/DELETE), and the
``o:errorDetails`` envelope parse.
"""

from __future__ import annotations

import json
import re

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import NetSuiteApiCredential
from weftlyflow.credentials.types.netsuite_api import account_host, sign_request
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.netsuite import NetSuiteNode
from weftlyflow.nodes.integrations.netsuite.operations import build_request

_CRED_ID: str = "cr_netsuite"
_PROJECT_ID: str = "pr_test"
_ACCOUNT: str = "1234567-sb1"
_HOST: str = "1234567-sb1.suitetalk.api.netsuite.com"
_BASE: str = f"https://{_HOST}"
_AUTH_RE: re.Pattern[str] = re.compile(
    r'^OAuth realm="1234567_SB1", '
    r'oauth_consumer_key="[^"]+", '
    r'oauth_nonce="[^"]+", '
    r'oauth_signature_method="HMAC-SHA256", '
    r'oauth_timestamp="\d+", '
    r'oauth_token="[^"]+", '
    r'oauth_version="1\.0", '
    r'oauth_signature="[^"]+"$',
)


def _resolver() -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.netsuite_api": NetSuiteApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.netsuite_api",
                {
                    "account_id": _ACCOUNT,
                    "consumer_key": "ck",
                    "consumer_secret": "cs",
                    "token_id": "ti",
                    "token_secret": "ts",
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


# --- signer primitives ----------------------------------------------


def test_account_host_lowercases_with_dashes() -> None:
    assert account_host("1234567-SB1") == _HOST


def test_account_host_rejects_empty() -> None:
    with pytest.raises(ValueError, match="'account_id' is required"):
        account_host("  ")


def test_sign_request_is_deterministic_with_fixed_nonce_and_timestamp() -> None:
    header = sign_request(
        method="GET",
        url=f"{_BASE}/services/rest/record/v1/customer/42",
        query={},
        account_id=_ACCOUNT,
        consumer_key="ck",
        consumer_secret="cs",
        token_id="ti",
        token_secret="ts",
        nonce="fixed-nonce",
        timestamp="1700000000",
    )
    again = sign_request(
        method="GET",
        url=f"{_BASE}/services/rest/record/v1/customer/42",
        query={},
        account_id=_ACCOUNT,
        consumer_key="ck",
        consumer_secret="cs",
        token_id="ti",
        token_secret="ts",
        nonce="fixed-nonce",
        timestamp="1700000000",
    )
    assert header == again
    assert 'realm="1234567_SB1"' in header
    assert 'oauth_signature_method="HMAC-SHA256"' in header
    assert 'oauth_nonce="fixed-nonce"' in header


def test_sign_request_changes_with_method() -> None:
    kwargs = {
        "url": f"{_BASE}/services/rest/record/v1/customer/42",
        "query": {},
        "account_id": _ACCOUNT,
        "consumer_key": "ck",
        "consumer_secret": "cs",
        "token_id": "ti",
        "token_secret": "ts",
        "nonce": "n",
        "timestamp": "1",
    }
    get_sig = sign_request(method="GET", **kwargs)
    delete_sig = sign_request(method="DELETE", **kwargs)
    assert get_sig != delete_sig


def test_sign_request_requires_all_fields() -> None:
    with pytest.raises(ValueError, match="all five OAuth fields"):
        sign_request(
            method="GET",
            url=_BASE,
            query={},
            account_id=_ACCOUNT,
            consumer_key="",
            consumer_secret="cs",
            token_id="ti",
            token_secret="ts",
        )


# --- suiteql_query ---------------------------------------------------


@respx.mock
async def test_suiteql_query_attaches_prefer_transient_and_signs() -> None:
    route = respx.post(
        f"{_BASE}/services/rest/query/v1/suiteql",
    ).mock(return_value=Response(200, json={"items": []}))
    node = Node(
        id="node_1",
        name="NetSuite",
        type="weftlyflow.netsuite",
        parameters={
            "operation": "suiteql_query",
            "query": "SELECT id FROM customer",
            "limit": 100,
            "offset": 0,
        },
        credentials={"netsuite_api": _CRED_ID},
    )
    await NetSuiteNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Prefer"] == "transient"
    assert _AUTH_RE.match(request.headers["Authorization"]) is not None
    body = json.loads(request.content)
    assert body == {"q": "SELECT id FROM customer"}
    assert request.url.params.get("limit") == "100"
    assert request.url.params.get("offset") == "0"


def test_suiteql_query_requires_query() -> None:
    with pytest.raises(ValueError, match="'query' is required"):
        build_request("suiteql_query", {})


def test_suiteql_query_rejects_negative_offset() -> None:
    with pytest.raises(ValueError, match="'offset' must be >= 0"):
        build_request(
            "suiteql_query",
            {"query": "SELECT 1", "offset": -1},
        )


# --- record_get / record_create / record_delete ---------------------


@respx.mock
async def test_record_get_uses_get_verb() -> None:
    route = respx.get(
        f"{_BASE}/services/rest/record/v1/customer/42",
    ).mock(return_value=Response(200, json={"id": "42"}))
    node = Node(
        id="node_1",
        name="NetSuite",
        type="weftlyflow.netsuite",
        parameters={
            "operation": "record_get",
            "record_type": "customer",
            "record_id": "42",
        },
        credentials={"netsuite_api": _CRED_ID},
    )
    await NetSuiteNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.method == "GET"


@respx.mock
async def test_record_create_posts_document_body() -> None:
    route = respx.post(
        f"{_BASE}/services/rest/record/v1/customer",
    ).mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="NetSuite",
        type="weftlyflow.netsuite",
        parameters={
            "operation": "record_create",
            "record_type": "customer",
            "document": {"companyName": "Acme"},
        },
        credentials={"netsuite_api": _CRED_ID},
    )
    await NetSuiteNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"companyName": "Acme"}


@respx.mock
async def test_record_delete_uses_delete_verb() -> None:
    route = respx.delete(
        f"{_BASE}/services/rest/record/v1/customer/42",
    ).mock(return_value=Response(204))
    node = Node(
        id="node_1",
        name="NetSuite",
        type="weftlyflow.netsuite",
        parameters={
            "operation": "record_delete",
            "record_type": "customer",
            "record_id": "42",
        },
        credentials={"netsuite_api": _CRED_ID},
    )
    await NetSuiteNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.method == "DELETE"


def test_record_create_requires_document() -> None:
    with pytest.raises(ValueError, match="'document' is required"):
        build_request(
            "record_create",
            {"record_type": "customer"},
        )


def test_record_get_requires_record_id() -> None:
    with pytest.raises(ValueError, match="'record_id' is required"):
        build_request(
            "record_get",
            {"record_type": "customer"},
        )


# --- errors ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_errordetails_envelope() -> None:
    respx.get(
        f"{_BASE}/services/rest/record/v1/customer/bad",
    ).mock(
        return_value=Response(
            404,
            json={
                "title": "Not Found",
                "o:errorDetails": [{"detail": "record not found"}],
            },
        ),
    )
    node = Node(
        id="node_1",
        name="NetSuite",
        type="weftlyflow.netsuite",
        parameters={
            "operation": "record_get",
            "record_type": "customer",
            "record_id": "bad",
        },
        credentials={"netsuite_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="record not found"):
        await NetSuiteNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="NetSuite",
        type="weftlyflow.netsuite",
        parameters={
            "operation": "record_get",
            "record_type": "customer",
            "record_id": "1",
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await NetSuiteNode().execute(_ctx_for(node), [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("hack", {})
