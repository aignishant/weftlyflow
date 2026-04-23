"""Per-operation request builders for the Square node.

Each builder returns ``(http_method, path, body, query)``. Paths are
prefixed with the ``/v2`` root.

Distinctive Square shapes:

* ``create_payment`` requires an ``idempotency_key`` per Square's
  exactly-once payment semantics — the builder generates one if absent
  but a caller can override it for retry safety.
* ``search_orders`` POSTs a JSON ``{"location_ids": [...], "query": {...}}``
  — listing-via-POST is unusual.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.square.constants import (
    OP_CREATE_CUSTOMER,
    OP_CREATE_PAYMENT,
    OP_GET_CUSTOMER,
    OP_LIST_CUSTOMERS,
    OP_LIST_PAYMENTS,
    OP_SEARCH_ORDERS,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Square: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_customers(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {}
    cursor = str(params.get("cursor") or "").strip()
    if cursor:
        query["cursor"] = cursor
    limit = params.get("limit")
    if limit is not None and limit != "":
        query["limit"] = _coerce_positive_int(limit, field="limit")
    return "GET", "/v2/customers", None, query


def _build_get_customer(params: dict[str, Any]) -> RequestSpec:
    customer_id = _required(params, "customer_id")
    return "GET", f"/v2/customers/{quote(customer_id, safe='')}", None, {}


def _build_create_customer(params: dict[str, Any]) -> RequestSpec:
    document = _coerce_document(params.get("document"))
    return "POST", "/v2/customers", document, {}


def _build_list_payments(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {}
    for source, target in (
        ("begin_time", "begin_time"),
        ("end_time", "end_time"),
        ("location_id", "location_id"),
        ("cursor", "cursor"),
    ):
        value = str(params.get(source) or "").strip()
        if value:
            query[target] = value
    limit = params.get("limit")
    if limit is not None and limit != "":
        query["limit"] = _coerce_positive_int(limit, field="limit")
    return "GET", "/v2/payments", None, query


def _build_create_payment(params: dict[str, Any]) -> RequestSpec:
    source_id = _required(params, "source_id")
    amount = params.get("amount")
    if amount is None or amount == "":
        msg = "Square: 'amount' is required (in smallest currency unit)"
        raise ValueError(msg)
    currency = _required(params, "currency").upper()
    idempotency_key = (
        str(params.get("idempotency_key") or "").strip() or secrets.token_hex(16)
    )
    body: dict[str, Any] = {
        "source_id": source_id,
        "idempotency_key": idempotency_key,
        "amount_money": {
            "amount": _coerce_positive_int(amount, field="amount"),
            "currency": currency,
        },
    }
    location_id = str(params.get("location_id") or "").strip()
    if location_id:
        body["location_id"] = location_id
    return "POST", "/v2/payments", body, {}


def _build_search_orders(params: dict[str, Any]) -> RequestSpec:
    location_ids = params.get("location_ids")
    if not location_ids:
        msg = "Square: 'location_ids' is required"
        raise ValueError(msg)
    if isinstance(location_ids, str):
        ids = [s.strip() for s in location_ids.split(",") if s.strip()]
    elif isinstance(location_ids, list):
        ids = [str(v).strip() for v in location_ids if str(v).strip()]
    else:
        msg = "Square: 'location_ids' must be a string or list"
        raise ValueError(msg)
    if not ids:
        msg = "Square: 'location_ids' is empty"
        raise ValueError(msg)
    body: dict[str, Any] = {"location_ids": ids}
    query_filter = params.get("query")
    if isinstance(query_filter, dict) and query_filter:
        body["query"] = query_filter
    cursor = str(params.get("cursor") or "").strip()
    if cursor:
        body["cursor"] = cursor
    limit = params.get("limit")
    if limit is not None and limit != "":
        body["limit"] = _coerce_positive_int(limit, field="limit")
    return "POST", "/v2/orders/search", body, {}


def _coerce_document(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        msg = "Square: 'document' is required"
        raise ValueError(msg)
    if not isinstance(raw, dict):
        msg = "Square: 'document' must be a JSON object"
        raise ValueError(msg)
    return raw


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Square: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"Square: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Square: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_CUSTOMERS: _build_list_customers,
    OP_GET_CUSTOMER: _build_get_customer,
    OP_CREATE_CUSTOMER: _build_create_customer,
    OP_LIST_PAYMENTS: _build_list_payments,
    OP_CREATE_PAYMENT: _build_create_payment,
    OP_SEARCH_ORDERS: _build_search_orders,
}
