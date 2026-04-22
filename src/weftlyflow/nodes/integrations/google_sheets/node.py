"""Google Sheets node — read ranges, append rows, update ranges.

Dispatches to Google's Sheets v4 REST API at
``https://sheets.googleapis.com``. Every request carries
``Authorization: Bearer <access_token>`` from a
:class:`~weftlyflow.credentials.types.google_sheets_oauth2.GoogleSheetsOAuth2Credential`.

Parameters (all expression-capable):

* ``operation`` — ``read_range``, ``append_row``, ``update_range``.
* ``spreadsheet_id`` — Google Sheets file id (from the URL).
* ``range`` — A1 notation, e.g. ``'Sheet1!A1:C10'``.
* ``values`` — list of rows; each row is a list of cell values. Required
  for ``append_row`` and ``update_range``.
* ``value_input_option`` — ``USER_ENTERED`` (default) or ``RAW``.

Output: one item per input item with ``operation``, ``status``, and the
parsed ``response`` dict. For ``read_range`` a convenience ``values`` key
lifts ``response["values"]``; for ``append_row`` the ``updated_range``,
``updated_rows``, and ``updated_cells`` fields from the response's
``updates`` object are surfaced at the top level.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    CredentialSlot,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.integrations.google_sheets.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    OP_APPEND_ROW,
    OP_READ_RANGE,
    OP_UPDATE_RANGE,
    SUPPORTED_OPERATIONS,
    VALUE_INPUT_RAW,
    VALUE_INPUT_USER_ENTERED,
)
from weftlyflow.nodes.integrations.google_sheets.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "google_sheets_oauth2"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.google_sheets_oauth2",)

log = structlog.get_logger(__name__)


class GoogleSheetsNode(BaseNode):
    """Dispatch a single Google Sheets REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.google_sheets",
        version=1,
        display_name="Google Sheets",
        description="Read ranges, append rows, and update ranges in a Google Sheet.",
        icon="icons/google-sheets.svg",
        category=NodeCategory.INTEGRATION,
        group=["productivity", "spreadsheet"],
        documentation_url="https://developers.google.com/sheets/api/reference/rest",
        credentials=[
            CredentialSlot(
                name=_CREDENTIAL_SLOT,
                required=True,
                credential_types=list(_CREDENTIAL_SLUGS),
            ),
        ],
        properties=[
            PropertySchema(
                name="operation",
                display_name="Operation",
                type="options",
                default=OP_READ_RANGE,
                required=True,
                options=[
                    PropertyOption(value=OP_READ_RANGE, label="Read Range"),
                    PropertyOption(value=OP_APPEND_ROW, label="Append Row"),
                    PropertyOption(value=OP_UPDATE_RANGE, label="Update Range"),
                ],
            ),
            PropertySchema(
                name="spreadsheet_id",
                display_name="Spreadsheet ID",
                type="string",
                required=True,
            ),
            PropertySchema(
                name="range",
                display_name="Range (A1 Notation)",
                type="string",
                required=True,
                placeholder="Sheet1!A1:C10",
            ),
            PropertySchema(
                name="values",
                display_name="Values",
                type="json",
                description="List of rows (each row is a list of cell values).",
            ),
            PropertySchema(
                name="value_input_option",
                display_name="Value Input Option",
                type="options",
                default=VALUE_INPUT_USER_ENTERED,
                options=[
                    PropertyOption(value=VALUE_INPUT_USER_ENTERED, label="User Entered"),
                    PropertyOption(value=VALUE_INPUT_RAW, label="Raw"),
                ],
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Google Sheets REST call per input item."""
        token = await _resolve_token(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(ctx, item, client=client, token=token, logger=bound),
                )
        return [results]


async def _resolve_token(ctx: ExecutionContext) -> str:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Google Sheets: a Google OAuth2 credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    _, payload = credential
    token = str(payload.get("access_token") or "").strip()
    if not token:
        msg = "Google Sheets: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return token


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    token: str,
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_READ_RANGE).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Google Sheets: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    try:
        response = await client.request(
            method,
            path,
            params=query or None,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        logger.error("google_sheets.request_failed", operation=operation, error=str(exc))
        msg = f"Google Sheets: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": payload,
    }
    if isinstance(payload, dict):
        if operation == OP_READ_RANGE:
            values = payload.get("values", [])
            result["values"] = values if isinstance(values, list) else []
        elif operation == OP_APPEND_ROW:
            updates = payload.get("updates")
            if isinstance(updates, dict):
                result["updated_range"] = str(updates.get("updatedRange", ""))
                result["updated_rows"] = int(updates.get("updatedRows") or 0)
                result["updated_cells"] = int(updates.get("updatedCells") or 0)
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "google_sheets.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Google Sheets {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("google_sheets.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
    return f"HTTP {status_code}"
