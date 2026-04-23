"""Unit tests for :class:`SalesforceNode`.

Exercises every supported operation against a respx-mocked Salesforce
REST endpoint. Verifies the distinctive per-org ``instance_url`` from
the credential (not a hardcoded host), the SOQL translation of
``list_records``, the ``errorCode: message`` array envelope parse, and
the PATCH verb Salesforce uses for updates.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import SalesforceApiCredential
from weftlyflow.credentials.types.salesforce_api import instance_url_from
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.salesforce import SalesforceNode
from weftlyflow.nodes.integrations.salesforce.operations import build_request

_CRED_ID: str = "cr_sf"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "sf-token"
_INSTANCE: str = "https://acme.my.salesforce.com"
_BASE: str = f"{_INSTANCE}/services/data/v58.0"


def _resolver(
    *,
    token: str = _TOKEN,
    instance_url: str = _INSTANCE,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.salesforce_api": SalesforceApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.salesforce_api",
                {"access_token": token, "instance_url": instance_url},
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


# --- list_records (SOQL translation) ---------------------------------


@respx.mock
async def test_list_records_hits_query_endpoint_with_soql() -> None:
    route = respx.get(f"{_BASE}/query").mock(
        return_value=Response(200, json={"records": []}),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.salesforce",
        parameters={
            "operation": "list_records",
            "sobject": "Account",
            "fields": "Id,Name,Industry",
            "where": "Industry = 'Tech'",
            "order_by": "Name ASC",
            "limit": 50,
        },
        credentials={"salesforce_api": _CRED_ID},
    )
    await SalesforceNode().execute(_ctx_for(node), [Item()])
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    soql = request.url.params.get("q")
    assert soql is not None
    assert "SELECT Id, Name, Industry FROM Account" in soql
    assert "WHERE Industry = 'Tech'" in soql
    assert "ORDER BY Name ASC" in soql
    assert "LIMIT 50" in soql


def test_list_records_rejects_sql_injection_in_sobject() -> None:
    with pytest.raises(ValueError, match="alphanumeric/underscore only"):
        build_request(
            "list_records",
            {"sobject": "Account; DROP TABLE users"},
        )


def test_list_records_defaults_fields_when_missing() -> None:
    _, _, _, query = build_request("list_records", {"sobject": "Contact"})
    assert "SELECT Id, Name FROM Contact" in query["q"]


# --- get_record ------------------------------------------------------


@respx.mock
async def test_get_record_targets_sobjects_path() -> None:
    route = respx.get(f"{_BASE}/sobjects/Account/001abc").mock(
        return_value=Response(200, json={"Id": "001abc"}),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.salesforce",
        parameters={
            "operation": "get_record",
            "sobject": "Account",
            "record_id": "001abc",
            "fields": "Id,Name",
        },
        credentials={"salesforce_api": _CRED_ID},
    )
    await SalesforceNode().execute(_ctx_for(node), [Item()])
    assert "fields=Id%2CName" in str(route.calls.last.request.url)


# --- create_record ---------------------------------------------------


@respx.mock
async def test_create_record_posts_document() -> None:
    route = respx.post(f"{_BASE}/sobjects/Contact").mock(
        return_value=Response(201, json={"id": "003abc"}),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.salesforce",
        parameters={
            "operation": "create_record",
            "sobject": "Contact",
            "document": {"LastName": "Lovelace", "Email": "ada@x.io"},
        },
        credentials={"salesforce_api": _CRED_ID},
    )
    await SalesforceNode().execute(_ctx_for(node), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"LastName": "Lovelace", "Email": "ada@x.io"}


def test_create_record_rejects_empty_document() -> None:
    with pytest.raises(ValueError, match="non-empty JSON object"):
        build_request(
            "create_record",
            {"sobject": "Contact", "document": {}},
        )


# --- update_record (PATCH) -------------------------------------------


@respx.mock
async def test_update_record_uses_patch_verb() -> None:
    route = respx.patch(f"{_BASE}/sobjects/Account/001abc").mock(
        return_value=Response(204),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.salesforce",
        parameters={
            "operation": "update_record",
            "sobject": "Account",
            "record_id": "001abc",
            "document": {"Industry": "Finance"},
        },
        credentials={"salesforce_api": _CRED_ID},
    )
    await SalesforceNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.method == "PATCH"


# --- delete_record ---------------------------------------------------


@respx.mock
async def test_delete_record_sends_delete_verb() -> None:
    route = respx.delete(f"{_BASE}/sobjects/Account/001abc").mock(
        return_value=Response(204),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.salesforce",
        parameters={
            "operation": "delete_record",
            "sobject": "Account",
            "record_id": "001abc",
        },
        credentials={"salesforce_api": _CRED_ID},
    )
    await SalesforceNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- raw SOQL query --------------------------------------------------


@respx.mock
async def test_query_passes_raw_soql() -> None:
    route = respx.get(f"{_BASE}/query").mock(
        return_value=Response(200, json={"records": []}),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.salesforce",
        parameters={
            "operation": "query",
            "soql": "SELECT Count() FROM Account",
        },
        credentials={"salesforce_api": _CRED_ID},
    )
    await SalesforceNode().execute(_ctx_for(node), [Item()])
    assert route.calls.last.request.url.params.get("q") == "SELECT Count() FROM Account"


# --- per-org instance URL -------------------------------------------


@respx.mock
async def test_alternate_instance_url_used_from_credential() -> None:
    alt = "https://other.my.salesforce.com"
    route = respx.get(f"{alt}/services/data/v58.0/query").mock(
        return_value=Response(200, json={"records": []}),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.salesforce",
        parameters={"operation": "list_records", "sobject": "Account"},
        credentials={"salesforce_api": _CRED_ID},
    )
    await SalesforceNode().execute(
        _ctx_for(node, resolver=_resolver(instance_url=alt)),
        [Item()],
    )
    assert route.called


def test_instance_url_from_adds_https_if_missing() -> None:
    assert instance_url_from("acme.my.salesforce.com") == "https://acme.my.salesforce.com"


def test_instance_url_from_rejects_empty() -> None:
    with pytest.raises(ValueError, match="'instance_url' is required"):
        instance_url_from("   ")


# --- API version override -------------------------------------------


@respx.mock
async def test_api_version_override_changes_path() -> None:
    route = respx.get(f"{_INSTANCE}/services/data/v60.0/query").mock(
        return_value=Response(200, json={"records": []}),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.salesforce",
        parameters={
            "operation": "list_records",
            "sobject": "Account",
            "api_version": "v60.0",
        },
        credentials={"salesforce_api": _CRED_ID},
    )
    await SalesforceNode().execute(_ctx_for(node), [Item()])
    assert route.called


def test_invalid_api_version_rejected() -> None:
    with pytest.raises(ValueError, match="'api_version' must look like"):
        build_request(
            "list_records",
            {"sobject": "Account", "api_version": "latest"},
        )


# --- errors ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_errorcode_and_message() -> None:
    respx.post(f"{_BASE}/sobjects/Contact").mock(
        return_value=Response(
            400,
            json=[{"errorCode": "REQUIRED_FIELD_MISSING", "message": "LastName"}],
        ),
    )
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.salesforce",
        parameters={
            "operation": "create_record",
            "sobject": "Contact",
            "document": {"Email": "x@y.io"},
        },
        credentials={"salesforce_api": _CRED_ID},
    )
    with pytest.raises(
        NodeExecutionError, match="REQUIRED_FIELD_MISSING: LastName",
    ):
        await SalesforceNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="SF",
        type="weftlyflow.salesforce",
        parameters={"operation": "list_records", "sobject": "Account"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await SalesforceNode().execute(_ctx_for(node), [Item()])


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("purge_universe", {})
