"""Alpaca Markets node — account, positions, orders, clock.

Dispatches against ``paper-api.alpaca.markets`` (paper) or
``api.alpaca.markets`` (live); the host is selected from the
``environment`` field on
:class:`~weftlyflow.credentials.types.alpaca_api.AlpacaApiCredential`,
so a single node definition can be flipped between paper and live by
swapping the credential rather than editing the workflow.

Parameters (all expression-capable):

* ``operation``  — ``get_account`` / ``list_positions`` /
  ``place_order`` / ``get_clock``.
* ``symbol``     — ticker to trade, e.g. ``AAPL``.
* ``side`` / ``order_type`` / ``qty`` / ``notional`` /
  ``limit_price`` / ``time_in_force`` / ``client_order_id`` —
  order fields.

Output: one item per input item with ``operation``, ``status``, and
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.credentials.types.alpaca_api import host_for
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    CredentialSlot,
    DisplayOptions,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.integrations.alpaca.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    OP_GET_ACCOUNT,
    OP_GET_CLOCK,
    OP_LIST_POSITIONS,
    OP_PLACE_ORDER,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    SIDE_BUY,
    SIDE_SELL,
    SUPPORTED_OPERATIONS,
    TIF_DAY,
    TIF_FOK,
    TIF_GTC,
    TIF_IOC,
)
from weftlyflow.nodes.integrations.alpaca.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "alpaca_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.alpaca_api",)

log = structlog.get_logger(__name__)


class AlpacaNode(BaseNode):
    """Dispatch a single Alpaca Markets REST call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.alpaca",
        version=1,
        display_name="Alpaca Markets",
        description="Account, positions, clock, and order management on Alpaca Markets.",
        icon="icons/alpaca.svg",
        category=NodeCategory.INTEGRATION,
        group=["finance"],
        documentation_url="https://docs.alpaca.markets/reference/",
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
                default=OP_GET_ACCOUNT,
                required=True,
                options=[
                    PropertyOption(value=OP_GET_ACCOUNT, label="Get Account"),
                    PropertyOption(value=OP_LIST_POSITIONS, label="List Positions"),
                    PropertyOption(value=OP_PLACE_ORDER, label="Place Order"),
                    PropertyOption(value=OP_GET_CLOCK, label="Get Clock"),
                ],
            ),
            PropertySchema(
                name="symbol",
                display_name="Symbol",
                type="string",
                description='Ticker, e.g. "AAPL".',
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
            PropertySchema(
                name="side",
                display_name="Side",
                type="options",
                default=SIDE_BUY,
                options=[
                    PropertyOption(value=SIDE_BUY, label="Buy"),
                    PropertyOption(value=SIDE_SELL, label="Sell"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
            PropertySchema(
                name="order_type",
                display_name="Order Type",
                type="options",
                default=ORDER_TYPE_MARKET,
                options=[
                    PropertyOption(value=ORDER_TYPE_MARKET, label="Market"),
                    PropertyOption(value=ORDER_TYPE_LIMIT, label="Limit"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
            PropertySchema(
                name="qty",
                display_name="Quantity",
                type="string",
                description="Shares to buy/sell (whole or fractional).",
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
            PropertySchema(
                name="notional",
                display_name="Notional (USD)",
                type="string",
                description="Alternative to qty — dollar amount to trade.",
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
            PropertySchema(
                name="limit_price",
                display_name="Limit Price",
                type="string",
                description="Required for limit orders.",
                display_options=DisplayOptions(
                    show={"operation": [OP_PLACE_ORDER], "order_type": [ORDER_TYPE_LIMIT]},
                ),
            ),
            PropertySchema(
                name="time_in_force",
                display_name="Time in Force",
                type="options",
                default=TIF_DAY,
                options=[
                    PropertyOption(value=TIF_DAY, label="Day"),
                    PropertyOption(value=TIF_GTC, label="Good Till Cancelled"),
                    PropertyOption(value=TIF_IOC, label="Immediate or Cancel"),
                    PropertyOption(value=TIF_FOK, label="Fill or Kill"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
            PropertySchema(
                name="client_order_id",
                display_name="Client Order ID",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_PLACE_ORDER]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Alpaca Markets call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        host = host_for(payload.get("environment"))
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=host, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, injector=injector,
                        creds=payload, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Alpaca: an alpaca_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    for key in ("api_key_id", "api_secret_key"):
        if not str(payload.get(key) or "").strip():
            msg = f"Alpaca: credential has an empty {key!r}"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_GET_ACCOUNT).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Alpaca: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = client.build_request(method, path, json=body, headers=headers)
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("alpaca.request_failed", operation=operation, error=str(exc))
        msg = f"Alpaca: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    parsed = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": parsed,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(parsed, response.status_code)
        logger.warning(
            "alpaca.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Alpaca {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("alpaca.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(parsed: Any, status_code: int) -> str:
    if isinstance(parsed, dict):
        for key in ("message", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status_code}"
