"""Unit tests for :class:`GoogleSheetsNode`.

Exercises every supported operation against a respx-mocked Sheets v4 REST
API. Verifies URL encoding of A1-notation ranges and that the
``valueInputOption`` query param defaults to ``USER_ENTERED``.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import GoogleSheetsOAuth2Credential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.google_sheets import GoogleSheetsNode
from weftlyflow.nodes.integrations.google_sheets.operations import build_request

_CRED_ID: str = "cr_gsheets"
_PROJECT_ID: str = "pr_test"


def _resolver(*, access_token: str = "ya29.abc") -> InMemoryCredentialResolver:
    payload: dict[str, object] = {
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "client_id": "id",
        "client_secret": "secret",
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "access_token": access_token,
    }
    return InMemoryCredentialResolver(
        types={"weftlyflow.google_sheets_oauth2": GoogleSheetsOAuth2Credential},
        rows={
            _CRED_ID: ("weftlyflow.google_sheets_oauth2", payload, _PROJECT_ID),
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


# --- read_range ------------------------------------------------------------


@respx.mock
async def test_read_range_surfaces_values_convenience_key() -> None:
    route = respx.get(
        "https://sheets.googleapis.com/v4/spreadsheets/sheet_1/values/Sheet1%21A1%3AB2",
    ).mock(
        return_value=Response(
            200, json={"range": "Sheet1!A1:B2", "values": [["a", "b"], ["c", "d"]]},
        ),
    )
    node = Node(
        id="node_1",
        name="Google Sheets",
        type="weftlyflow.google_sheets",
        parameters={
            "operation": "read_range",
            "spreadsheet_id": "sheet_1",
            "range": "Sheet1!A1:B2",
        },
        credentials={"google_sheets_oauth2": _CRED_ID},
    )
    out = await GoogleSheetsNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["values"] == [["a", "b"], ["c", "d"]]
    headers = route.calls.last.request.headers
    assert headers["authorization"] == "Bearer ya29.abc"


@respx.mock
async def test_read_range_encodes_sheet_names_with_spaces() -> None:
    route = respx.get(
        "https://sheets.googleapis.com/v4/spreadsheets/sheet_1/values/Sheet%201%21A1",
    ).mock(return_value=Response(200, json={"values": []}))
    node = Node(
        id="node_1",
        name="Google Sheets",
        type="weftlyflow.google_sheets",
        parameters={
            "operation": "read_range",
            "spreadsheet_id": "sheet_1",
            "range": "Sheet 1!A1",
        },
        credentials={"google_sheets_oauth2": _CRED_ID},
    )
    await GoogleSheetsNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called


# --- append_row ------------------------------------------------------------


@respx.mock
async def test_append_row_posts_values_and_default_value_input() -> None:
    route = respx.post(
        "https://sheets.googleapis.com/v4/spreadsheets/sheet_1/values/Sheet1%21A1:append",
    ).mock(
        return_value=Response(
            200,
            json={
                "updates": {
                    "updatedRange": "Sheet1!A2:B2",
                    "updatedRows": 1,
                    "updatedCells": 2,
                },
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Google Sheets",
        type="weftlyflow.google_sheets",
        parameters={
            "operation": "append_row",
            "spreadsheet_id": "sheet_1",
            "range": "Sheet1!A1",
            "values": [["hi", "there"]],
        },
        credentials={"google_sheets_oauth2": _CRED_ID},
    )
    out = await GoogleSheetsNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    [result] = out[0]
    assert result.json["updated_range"] == "Sheet1!A2:B2"
    assert result.json["updated_rows"] == 1
    assert result.json["updated_cells"] == 2
    body = json.loads(route.calls.last.request.content)
    assert body["values"] == [["hi", "there"]]
    assert body["majorDimension"] == "ROWS"
    assert route.calls.last.request.url.params["valueInputOption"] == "USER_ENTERED"


@respx.mock
async def test_append_row_respects_raw_value_input_option() -> None:
    route = respx.post(
        "https://sheets.googleapis.com/v4/spreadsheets/sheet_1/values/Sheet1%21A1:append",
    ).mock(return_value=Response(200, json={"updates": {}}))
    node = Node(
        id="node_1",
        name="Google Sheets",
        type="weftlyflow.google_sheets",
        parameters={
            "operation": "append_row",
            "spreadsheet_id": "sheet_1",
            "range": "Sheet1!A1",
            "values": [["42"]],
            "value_input_option": "raw",
        },
        credentials={"google_sheets_oauth2": _CRED_ID},
    )
    await GoogleSheetsNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.calls.last.request.url.params["valueInputOption"] == "RAW"


# --- update_range ---------------------------------------------------------


@respx.mock
async def test_update_range_issues_put_request() -> None:
    route = respx.put(
        "https://sheets.googleapis.com/v4/spreadsheets/sheet_1/values/Sheet1%21A1%3AB1",
    ).mock(return_value=Response(200, json={"updatedCells": 2}))
    node = Node(
        id="node_1",
        name="Google Sheets",
        type="weftlyflow.google_sheets",
        parameters={
            "operation": "update_range",
            "spreadsheet_id": "sheet_1",
            "range": "Sheet1!A1:B1",
            "values": [["x", "y"]],
        },
        credentials={"google_sheets_oauth2": _CRED_ID},
    )
    await GoogleSheetsNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    assert route.called
    assert route.calls.last.request.method == "PUT"


# --- error paths -----------------------------------------------------------


@respx.mock
async def test_api_error_surfaces_google_message() -> None:
    respx.get(
        "https://sheets.googleapis.com/v4/spreadsheets/sheet_1/values/A1",
    ).mock(
        return_value=Response(
            403,
            json={"error": {"message": "caller does not have permission"}},
        ),
    )
    node = Node(
        id="node_1",
        name="Google Sheets",
        type="weftlyflow.google_sheets",
        parameters={
            "operation": "read_range",
            "spreadsheet_id": "sheet_1",
            "range": "A1",
        },
        credentials={"google_sheets_oauth2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="does not have permission"):
        await GoogleSheetsNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Google Sheets",
        type="weftlyflow.google_sheets",
        parameters={
            "operation": "read_range",
            "spreadsheet_id": "sheet_1",
            "range": "A1",
        },
    )
    with pytest.raises(NodeExecutionError, match="Google OAuth2 credential"):
        await GoogleSheetsNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_access_token_raises() -> None:
    node = Node(
        id="node_1",
        name="Google Sheets",
        type="weftlyflow.google_sheets",
        parameters={
            "operation": "read_range",
            "spreadsheet_id": "sheet_1",
            "range": "A1",
        },
        credentials={"google_sheets_oauth2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'access_token'"):
        await GoogleSheetsNode().execute(
            _ctx_for(node, resolver=_resolver(access_token="")), [Item()],
        )


# --- direct builder unit tests --------------------------------------------


def test_build_request_rejects_empty_values() -> None:
    with pytest.raises(ValueError, match="'values'"):
        build_request(
            "append_row",
            {"spreadsheet_id": "s", "range": "A1", "values": []},
        )


def test_build_request_rejects_invalid_value_input_option() -> None:
    with pytest.raises(ValueError, match="value_input_option"):
        build_request(
            "append_row",
            {
                "spreadsheet_id": "s",
                "range": "A1",
                "values": [[1]],
                "value_input_option": "bogus",
            },
        )


def test_build_request_requires_spreadsheet_id() -> None:
    with pytest.raises(ValueError, match="spreadsheet_id"):
        build_request("read_range", {"range": "A1"})


def test_build_request_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("eat_lunch", {})
