"""Unit tests for :class:`SnowflakeNode`.

Exercises every supported operation against a respx-mocked Snowflake
SQL API v2 endpoint. Verifies the distinctive
``X-Snowflake-Authorization-Token-Type`` header pair (Bearer +
declared token kind), the per-account host derived from the
credential (``<account>.snowflakecomputing.com``), the positional
bindings shape, the ``?async=true`` flag for fire-and-poll execution,
the SQLSTATE error envelope, and the handle-based
get_status/cancel paths.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import SnowflakeApiCredential
from weftlyflow.credentials.types.snowflake_api import account_host_from
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.snowflake import SnowflakeNode
from weftlyflow.nodes.integrations.snowflake.operations import build_request

_CRED_ID: str = "cr_snowflake"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "sf-jwt"
_ACCOUNT: str = "xy12345.us-east-1"
_HOST: str = f"https://{_ACCOUNT}.snowflakecomputing.com"


def _resolver(
    *,
    token: str = _TOKEN,
    token_type: str = "KEYPAIR_JWT",
    account: str = _ACCOUNT,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.snowflake_api": SnowflakeApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.snowflake_api",
                {
                    "token": token,
                    "token_type": token_type,
                    "account": account,
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


# --- execute ---------------------------------------------------------


@respx.mock
async def test_execute_posts_statement_with_token_type_header() -> None:
    route = respx.post(f"{_HOST}/api/v2/statements").mock(
        return_value=Response(200, json={"resultSetMetaData": {}}),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.snowflake",
        parameters={
            "operation": "execute",
            "statement": "SELECT 1",
            "warehouse": "WH",
            "database": "DB",
            "schema": "PUBLIC",
            "role": "ANALYST",
            "timeout": 30,
        },
        credentials={"snowflake_api": _CRED_ID},
    )
    await SnowflakeNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert request.headers["X-Snowflake-Authorization-Token-Type"] == "KEYPAIR_JWT"
    body = json.loads(request.content)
    assert body == {
        "statement": "SELECT 1",
        "warehouse": "WH",
        "database": "DB",
        "schema": "PUBLIC",
        "role": "ANALYST",
        "timeout": 30,
    }


@respx.mock
async def test_execute_oauth_token_type_propagated() -> None:
    route = respx.post(f"{_HOST}/api/v2/statements").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.snowflake",
        parameters={"operation": "execute", "statement": "SELECT 1"},
        credentials={"snowflake_api": _CRED_ID},
    )
    await SnowflakeNode().execute(
        _ctx_for(node, resolver=_resolver(token_type="OAUTH")),
        [Item()],
    )
    assert (
        route.calls.last.request.headers["X-Snowflake-Authorization-Token-Type"]
        == "OAUTH"
    )


@respx.mock
async def test_execute_async_flag_appended_as_query() -> None:
    route = respx.post(f"{_HOST}/api/v2/statements").mock(
        return_value=Response(202, json={"statementHandle": "sh-1"}),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.snowflake",
        parameters={
            "operation": "execute",
            "statement": "CALL long_running()",
            "async_exec": True,
            "request_id": "req-42",
        },
        credentials={"snowflake_api": _CRED_ID},
    )
    await SnowflakeNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params.get("async") == "true"
    assert params.get("requestId") == "req-42"


def test_execute_bindings_inferred_types() -> None:
    _, _, body, _ = build_request(
        "execute",
        {"statement": "SELECT ?", "bindings": {"1": 42, "2": "hello"}},
    )
    assert body is not None
    assert body["bindings"] == {
        "1": {"type": "FIXED", "value": "42"},
        "2": {"type": "TEXT", "value": "hello"},
    }


def test_execute_bindings_explicit_shape() -> None:
    _, _, body, _ = build_request(
        "execute",
        {
            "statement": "SELECT ?",
            "bindings": {"1": {"type": "DATE", "value": "2026-04-23"}},
        },
    )
    assert body is not None
    assert body["bindings"] == {"1": {"type": "DATE", "value": "2026-04-23"}}


def test_execute_bindings_reject_malformed_pair() -> None:
    with pytest.raises(ValueError, match=r"type.*value"):
        build_request(
            "execute",
            {"statement": "x", "bindings": {"1": {"type": "TEXT"}}},
        )


def test_execute_requires_statement() -> None:
    with pytest.raises(ValueError, match="'statement' is required"):
        build_request("execute", {})


# --- get_status (handle) --------------------------------------------


@respx.mock
async def test_get_status_hits_handle_path() -> None:
    route = respx.get(f"{_HOST}/api/v2/statements/sh-42").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.snowflake",
        parameters={
            "operation": "get_status",
            "statement_handle": "sh-42",
            "partition": 2,
            "page_size": 500,
        },
        credentials={"snowflake_api": _CRED_ID},
    )
    await SnowflakeNode().execute(_ctx_for(node), [Item()])
    params = route.calls.last.request.url.params
    assert params.get("partition") == "2"
    assert params.get("pageSize") == "500"


# --- cancel ----------------------------------------------------------


@respx.mock
async def test_cancel_posts_to_cancel_path() -> None:
    route = respx.post(f"{_HOST}/api/v2/statements/sh-42/cancel").mock(
        return_value=Response(200, json={}),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.snowflake",
        parameters={
            "operation": "cancel",
            "statement_handle": "sh-42",
        },
        credentials={"snowflake_api": _CRED_ID},
    )
    await SnowflakeNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- account host normalization -------------------------------------


def test_account_host_from_bare_locator() -> None:
    assert (
        account_host_from("xy12345")
        == "https://xy12345.snowflakecomputing.com"
    )


def test_account_host_from_fully_qualified() -> None:
    assert (
        account_host_from("xy12345.us-east-1")
        == "https://xy12345.us-east-1.snowflakecomputing.com"
    )


def test_account_host_from_full_host_passthrough() -> None:
    assert (
        account_host_from("xy12345.snowflakecomputing.com")
        == "https://xy12345.snowflakecomputing.com"
    )


def test_account_host_from_rejects_empty() -> None:
    with pytest.raises(ValueError, match="'account' is required"):
        account_host_from("   ")


# --- errors ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_code_and_message() -> None:
    respx.post(f"{_HOST}/api/v2/statements").mock(
        return_value=Response(
            400,
            json={"code": "002003", "message": "SQL compilation error"},
        ),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.snowflake",
        parameters={"operation": "execute", "statement": "INVALID"},
        credentials={"snowflake_api": _CRED_ID},
    )
    with pytest.raises(
        NodeExecutionError, match=r"002003: SQL compilation error",
    ):
        await SnowflakeNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.snowflake",
        parameters={"operation": "execute", "statement": "SELECT 1"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await SnowflakeNode().execute(_ctx_for(node), [Item()])


async def test_invalid_token_type_raises() -> None:
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.snowflake",
        parameters={"operation": "execute", "statement": "SELECT 1"},
        credentials={"snowflake_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match=r"KEYPAIR_JWT.*OAUTH"):
        await SnowflakeNode().execute(
            _ctx_for(node, resolver=_resolver(token_type="basic")),
            [Item()],
        )


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("drop_database", {})
