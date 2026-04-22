"""Unit tests for :class:`AirtableNode`.

Exercises every supported operation against a respx-mocked Airtable v0
REST API. Verifies URL encoding of table names with spaces and the
``records`` convenience key on ``list_records``.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import BearerTokenCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.airtable import AirtableNode
from weftlyflow.nodes.integrations.airtable.operations import build_request

_CRED_ID: str = "cr_at"
_PROJECT_ID: str = "pr_test"
_BASE_URL: str = "https://api.airtable.com/v0/appAAA/Tasks"


def _resolver(*, token: str = "pat_abc") -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.bearer_token": BearerTokenCredential},
        rows={_CRED_ID: ("weftlyflow.bearer_token", {"token": token}, _PROJECT_ID)},
    )


def _ctx_for(
    node: Node,
    *,
    inputs: list[Item] | None = None,
    resolver: InMemoryCredentialResolver | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [], project_id=_PROJECT_ID)
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": list(inputs or [])},
        credential_resolver=resolver,
    )


# --- list_records ---------------------------------------------------------


@respx.mock
async def test_list_records_surfaces_records_convenience_key() -> None:
    route = respx.get(_BASE_URL).mock(
        return_value=Response(
            200,
            json={"records": [{"id": "rec1"}, {"id": "rec2"}], "offset": "next"},
        ),
    )
    node = Node(
        id="node_1",
        name="Airtable",
        type="weftlyflow.airtable",
        parameters={
            "operation": "list_records",
            "base_id": "appAAA",
            "table": "Tasks",
            "view": "Grid",
            "filter_by_formula": "Status='Open'",
            "page_size": 50,
            "max_records": 200,
            "offset": "prev",
        },
        credentials={"airtable_api": _CRED_ID},
    )
    out = await AirtableNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert [r["id"] for r in result.json["records"]] == ["rec1", "rec2"]
    query = dict(route.calls.last.request.url.params)
    assert query["view"] == "Grid"
    assert query["filterByFormula"] == "Status='Open'"
    assert query["pageSize"] == "50"
    assert query["maxRecords"] == "200"
    assert query["offset"] == "prev"
    assert route.calls.last.request.headers["authorization"] == "Bearer pat_abc"


@respx.mock
async def test_list_records_encodes_table_names_with_spaces() -> None:
    route = respx.get(
        "https://api.airtable.com/v0/appAAA/Project%20Tasks",
    ).mock(return_value=Response(200, json={"records": []}))
    node = Node(
        id="node_1",
        name="Airtable",
        type="weftlyflow.airtable",
        parameters={
            "operation": "list_records",
            "base_id": "appAAA",
            "table": "Project Tasks",
        },
        credentials={"airtable_api": _CRED_ID},
    )
    await AirtableNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- get_record / update / delete ----------------------------------------


@respx.mock
async def test_get_record_is_a_get() -> None:
    route = respx.get(f"{_BASE_URL}/rec1").mock(
        return_value=Response(200, json={"id": "rec1", "fields": {"Name": "x"}}),
    )
    node = Node(
        id="node_1",
        name="Airtable",
        type="weftlyflow.airtable",
        parameters={
            "operation": "get_record",
            "base_id": "appAAA",
            "table": "Tasks",
            "record_id": "rec1",
        },
        credentials={"airtable_api": _CRED_ID},
    )
    out = await AirtableNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["response"]["id"] == "rec1"
    assert route.called


@respx.mock
async def test_create_records_posts_fields_and_typecast() -> None:
    route = respx.post(_BASE_URL).mock(
        return_value=Response(200, json={"records": [{"id": "rec_new"}]}),
    )
    node = Node(
        id="node_1",
        name="Airtable",
        type="weftlyflow.airtable",
        parameters={
            "operation": "create_records",
            "base_id": "appAAA",
            "table": "Tasks",
            "records": [{"fields": {"Name": "a"}}, {"fields": {"Name": "b"}}],
            "typecast": True,
        },
        credentials={"airtable_api": _CRED_ID},
    )
    await AirtableNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body["typecast"] is True
    assert [r["fields"]["Name"] for r in body["records"]] == ["a", "b"]


@respx.mock
async def test_update_record_patches_fields() -> None:
    route = respx.patch(f"{_BASE_URL}/rec1").mock(
        return_value=Response(200, json={"id": "rec1"}),
    )
    node = Node(
        id="node_1",
        name="Airtable",
        type="weftlyflow.airtable",
        parameters={
            "operation": "update_record",
            "base_id": "appAAA",
            "table": "Tasks",
            "record_id": "rec1",
            "fields": {"Status": "Done"},
        },
        credentials={"airtable_api": _CRED_ID},
    )
    await AirtableNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"fields": {"Status": "Done"}}


@respx.mock
async def test_delete_record_is_a_delete() -> None:
    route = respx.delete(f"{_BASE_URL}/rec1").mock(
        return_value=Response(200, json={"deleted": True, "id": "rec1"}),
    )
    node = Node(
        id="node_1",
        name="Airtable",
        type="weftlyflow.airtable",
        parameters={
            "operation": "delete_record",
            "base_id": "appAAA",
            "table": "Tasks",
            "record_id": "rec1",
        },
        credentials={"airtable_api": _CRED_ID},
    )
    await AirtableNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- error paths ----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_message() -> None:
    respx.get(_BASE_URL).mock(
        return_value=Response(
            422,
            json={"error": {"type": "INVALID_REQUEST", "message": "bad formula"}},
        ),
    )
    node = Node(
        id="node_1",
        name="Airtable",
        type="weftlyflow.airtable",
        parameters={
            "operation": "list_records",
            "base_id": "appAAA",
            "table": "Tasks",
        },
        credentials={"airtable_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="bad formula"):
        await AirtableNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Airtable",
        type="weftlyflow.airtable",
        parameters={
            "operation": "list_records",
            "base_id": "appAAA",
            "table": "Tasks",
        },
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await AirtableNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


# --- direct builder unit tests --------------------------------------------


def test_build_request_create_records_rejects_too_many() -> None:
    with pytest.raises(ValueError, match="at most 10"):
        build_request(
            "create_records",
            {
                "base_id": "appAAA",
                "table": "Tasks",
                "records": [{"fields": {"Name": str(i)}} for i in range(11)],
            },
        )


def test_build_request_update_record_requires_fields_object() -> None:
    with pytest.raises(ValueError, match="fields"):
        build_request(
            "update_record",
            {
                "base_id": "appAAA",
                "table": "Tasks",
                "record_id": "rec1",
                "fields": "nope",
            },
        )


def test_build_request_caps_page_size() -> None:
    _, _, _, query = build_request(
        "list_records",
        {"base_id": "appAAA", "table": "Tasks", "page_size": 9999},
    )
    assert query["pageSize"] == 100


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("eat_lunch", {})
