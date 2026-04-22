"""Unit tests for :class:`ZohoCrmNode`.

Exercises every supported operation against a respx-mocked Zoho v6 REST
API. Verifies the distinctive ``Authorization: Zoho-oauthtoken <token>``
header (not ``Bearer``), the DC-aware host composition via
:func:`host_for`, the ``{"data": [...]}`` envelope on create/update,
the ``fields_filter`` → ``fields`` query normalization on list
operations, and the search-key exclusivity rule.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import ZohoCrmOAuth2Credential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.zoho_crm import ZohoCrmNode
from weftlyflow.nodes.integrations.zoho_crm.operations import build_request

_CRED_ID: str = "cr_zh"
_PROJECT_ID: str = "pr_test"


def _resolver(
    *,
    access_token: str = "zoho-tok",
    datacenter: str = "us",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.zoho_crm_oauth2": ZohoCrmOAuth2Credential},
        rows={
            _CRED_ID: (
                "weftlyflow.zoho_crm_oauth2",
                {"access_token": access_token, "datacenter": datacenter},
                _PROJECT_ID,
            ),
        },
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


def _base(dc: str = "us") -> str:
    hosts = {
        "us": "www.zohoapis.com",
        "eu": "www.zohoapis.eu",
        "in": "www.zohoapis.in",
        "au": "www.zohoapis.com.au",
        "jp": "www.zohoapis.jp",
        "cn": "www.zohoapis.com.cn",
    }
    return f"https://{hosts[dc]}/crm/v6"


# --- list_records -------------------------------------------------------


@respx.mock
async def test_list_records_sends_zoho_oauthtoken_header() -> None:
    route = respx.get(f"{_base()}/Leads").mock(
        return_value=Response(200, json={"data": [{"id": "1"}]}),
    )
    node = Node(
        id="node_1",
        name="Zoho",
        type="weftlyflow.zoho_crm",
        parameters={
            "operation": "list_records",
            "module": "Leads",
            "per_page": 25,
        },
        credentials={"zoho_crm_oauth2": _CRED_ID},
    )
    out = await ZohoCrmNode().execute(
        _ctx_for(node, resolver=_resolver()), [Item()],
    )
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Zoho-oauthtoken zoho-tok"
    assert "authorization" in request.headers
    assert "bearer" not in request.headers["Authorization"].lower()
    assert "per_page=25" in str(request.url)
    [result] = out[0]
    assert result.json["data"] == [{"id": "1"}]


@respx.mock
async def test_list_records_normalizes_fields_filter_into_query() -> None:
    route = respx.get(f"{_base()}/Contacts").mock(
        return_value=Response(200, json={"data": []}),
    )
    node = Node(
        id="node_1",
        name="Zoho",
        type="weftlyflow.zoho_crm",
        parameters={
            "operation": "list_records",
            "module": "Contacts",
            "fields_filter": "First_Name,Last_Name,Email",
        },
        credentials={"zoho_crm_oauth2": _CRED_ID},
    )
    await ZohoCrmNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    url = str(route.calls.last.request.url)
    assert "fields=First_Name%2CLast_Name%2CEmail" in url or (
        "fields=First_Name,Last_Name,Email" in url
    )


# --- get_record ---------------------------------------------------------


@respx.mock
async def test_get_record_targets_dc_host_for_eu() -> None:
    route = respx.get(f"{_base('eu')}/Leads/9001").mock(
        return_value=Response(200, json={"data": [{"id": "9001"}]}),
    )
    node = Node(
        id="node_1",
        name="Zoho",
        type="weftlyflow.zoho_crm",
        parameters={
            "operation": "get_record",
            "module": "Leads",
            "record_id": "9001",
        },
        credentials={"zoho_crm_oauth2": _CRED_ID},
    )
    await ZohoCrmNode().execute(
        _ctx_for(node, resolver=_resolver(datacenter="eu")), [Item()],
    )
    assert route.called


# --- create_record ------------------------------------------------------


@respx.mock
async def test_create_record_wraps_fields_in_data_envelope() -> None:
    route = respx.post(f"{_base()}/Leads").mock(
        return_value=Response(201, json={"data": [{"id": "new"}]}),
    )
    node = Node(
        id="node_1",
        name="Zoho",
        type="weftlyflow.zoho_crm",
        parameters={
            "operation": "create_record",
            "module": "Leads",
            "fields": {"Last_Name": "Doe", "Company": "Acme"},
            "trigger": "workflow, approval",
        },
        credentials={"zoho_crm_oauth2": _CRED_ID},
    )
    await ZohoCrmNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "data": [{"Last_Name": "Doe", "Company": "Acme"}],
        "trigger": ["workflow", "approval"],
    }


def test_build_create_requires_non_empty_fields() -> None:
    with pytest.raises(ValueError, match="'fields'"):
        build_request("create_record", {"module": "Leads", "fields": {}})


# --- update_record ------------------------------------------------------


@respx.mock
async def test_update_record_embeds_id_in_data_envelope() -> None:
    route = respx.put(f"{_base()}/Leads/42").mock(
        return_value=Response(200, json={"data": [{"id": "42"}]}),
    )
    node = Node(
        id="node_1",
        name="Zoho",
        type="weftlyflow.zoho_crm",
        parameters={
            "operation": "update_record",
            "module": "Leads",
            "record_id": "42",
            "fields": {"Last_Name": "Smith"},
        },
        credentials={"zoho_crm_oauth2": _CRED_ID},
    )
    await ZohoCrmNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    body = json.loads(route.calls.last.request.content)
    assert body == {"data": [{"Last_Name": "Smith", "id": "42"}]}


# --- delete_record ------------------------------------------------------


@respx.mock
async def test_delete_record_issues_delete_verb() -> None:
    route = respx.delete(f"{_base()}/Leads/42").mock(
        return_value=Response(200, json={"data": [{"id": "42"}]}),
    )
    node = Node(
        id="node_1",
        name="Zoho",
        type="weftlyflow.zoho_crm",
        parameters={
            "operation": "delete_record",
            "module": "Leads",
            "record_id": "42",
        },
        credentials={"zoho_crm_oauth2": _CRED_ID},
    )
    await ZohoCrmNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- search_records -----------------------------------------------------


@respx.mock
async def test_search_records_forwards_single_key() -> None:
    route = respx.get(f"{_base()}/Leads/search").mock(
        return_value=Response(200, json={"data": [{"id": "3"}]}),
    )
    node = Node(
        id="node_1",
        name="Zoho",
        type="weftlyflow.zoho_crm",
        parameters={
            "operation": "search_records",
            "module": "Leads",
            "email": "ada@example.com",
        },
        credentials={"zoho_crm_oauth2": _CRED_ID},
    )
    await ZohoCrmNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    url = str(route.calls.last.request.url)
    assert "email=ada%40example.com" in url or "email=ada@example.com" in url


def test_search_requires_exactly_one_key() -> None:
    with pytest.raises(ValueError, match="one of"):
        build_request("search_records", {"module": "Leads"})
    with pytest.raises(ValueError, match="only one"):
        build_request(
            "search_records",
            {"module": "Leads", "email": "a@x.io", "word": "hello"},
        )


# --- errors / credentials -----------------------------------------------


@respx.mock
async def test_api_error_surfaces_code_and_message() -> None:
    respx.get(f"{_base()}/Leads").mock(
        return_value=Response(
            401,
            json={"code": "INVALID_TOKEN", "message": "token expired"},
        ),
    )
    node = Node(
        id="node_1",
        name="Zoho",
        type="weftlyflow.zoho_crm",
        parameters={"operation": "list_records", "module": "Leads"},
        credentials={"zoho_crm_oauth2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="INVALID_TOKEN: token expired"):
        await ZohoCrmNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Zoho",
        type="weftlyflow.zoho_crm",
        parameters={"operation": "list_records", "module": "Leads"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await ZohoCrmNode().execute(
            _ctx_for(node, resolver=_resolver()), [Item()],
        )


async def test_unknown_datacenter_raises() -> None:
    node = Node(
        id="node_1",
        name="Zoho",
        type="weftlyflow.zoho_crm",
        parameters={"operation": "list_records", "module": "Leads"},
        credentials={"zoho_crm_oauth2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="unknown datacenter"):
        await ZohoCrmNode().execute(
            _ctx_for(node, resolver=_resolver(datacenter="xx")), [Item()],
        )


# --- direct builder unit tests ------------------------------------------


def test_build_list_caps_per_page_at_max() -> None:
    _, _, _, query = build_request(
        "list_records", {"module": "Leads", "per_page": 9_999},
    )
    assert query["per_page"] == 200


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("blow_up_crm", {"module": "Leads"})
