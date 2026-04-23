"""Per-operation request builders for the PayPal node.

Each builder returns ``(http_method, path, body, query, request_id)``
where ``request_id`` is the value to set on the ``PayPal-Request-Id``
header for write operations (idempotency). ``None`` means no header.

Distinctive PayPal shapes:

* ``create_order`` requires the v2 Orders payload with ``intent`` and
  ``purchase_units[].amount.{currency_code, value}`` — distinct from
  Stripe's amount-in-cents convention.
* ``capture_order`` POSTs to ``/v2/checkout/orders/{id}/capture`` with
  an empty body — the operation itself is the trigger.
* All write operations carry an idempotency key so retried requests
  cannot duplicate state.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.paypal.constants import (
    OP_CAPTURE_ORDER,
    OP_CREATE_ORDER,
    OP_GET_INVOICE,
    OP_GET_ORDER,
    OP_LIST_INVOICES,
    OP_REFUND_CAPTURE,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any], str | None]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"PayPal: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_create_order(params: dict[str, Any]) -> RequestSpec:
    intent = str(params.get("intent") or "CAPTURE").strip().upper()
    currency = _required(params, "currency").upper()
    value = _required(params, "amount")
    body: dict[str, Any] = {
        "intent": intent,
        "purchase_units": [
            {"amount": {"currency_code": currency, "value": value}},
        ],
    }
    reference_id = str(params.get("reference_id") or "").strip()
    if reference_id:
        body["purchase_units"][0]["reference_id"] = reference_id
    return "POST", "/v2/checkout/orders", body, {}, _idempotency_key(params)


def _build_get_order(params: dict[str, Any]) -> RequestSpec:
    order_id = _required(params, "order_id")
    return "GET", f"/v2/checkout/orders/{quote(order_id, safe='')}", None, {}, None


def _build_capture_order(params: dict[str, Any]) -> RequestSpec:
    order_id = _required(params, "order_id")
    path = f"/v2/checkout/orders/{quote(order_id, safe='')}/capture"
    return "POST", path, {}, {}, _idempotency_key(params)


def _build_refund_capture(params: dict[str, Any]) -> RequestSpec:
    capture_id = _required(params, "capture_id")
    body: dict[str, Any] = {}
    amount = str(params.get("amount") or "").strip()
    currency = str(params.get("currency") or "").strip().upper()
    if amount and currency:
        body["amount"] = {"value": amount, "currency_code": currency}
    note = str(params.get("note_to_payer") or "").strip()
    if note:
        body["note_to_payer"] = note
    path = f"/v2/payments/captures/{quote(capture_id, safe='')}/refund"
    payload = body if body else {}
    return "POST", path, payload, {}, _idempotency_key(params)


def _build_list_invoices(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {}
    page = params.get("page")
    if page not in (None, ""):
        query["page"] = _coerce_positive_int(page, field="page")
    page_size = params.get("page_size")
    if page_size not in (None, ""):
        query["page_size"] = _coerce_positive_int(page_size, field="page_size")
    total_required = params.get("total_required")
    if isinstance(total_required, bool):
        query["total_required"] = "true" if total_required else "false"
    return "GET", "/v2/invoicing/invoices", None, query, None


def _build_get_invoice(params: dict[str, Any]) -> RequestSpec:
    invoice_id = _required(params, "invoice_id")
    return "GET", f"/v2/invoicing/invoices/{quote(invoice_id, safe='')}", None, {}, None


def _idempotency_key(params: dict[str, Any]) -> str:
    explicit = str(params.get("request_id") or "").strip()
    return explicit or secrets.token_hex(16)


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"PayPal: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"PayPal: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"PayPal: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_CREATE_ORDER: _build_create_order,
    OP_GET_ORDER: _build_get_order,
    OP_CAPTURE_ORDER: _build_capture_order,
    OP_REFUND_CAPTURE: _build_refund_capture,
    OP_LIST_INVOICES: _build_list_invoices,
    OP_GET_INVOICE: _build_get_invoice,
}
