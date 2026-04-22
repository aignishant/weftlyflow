"""Per-operation request builders for the Stripe node.

Each builder returns ``(http_method, path, form_fields, query_params)``.
Stripe expects ``application/x-www-form-urlencoded`` bodies (not JSON) —
``form_fields`` is a flat mapping that the dispatcher encodes with
:class:`httpx.QueryParams`. Nested metadata is expressed with bracketed
keys like ``metadata[source]``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.stripe.constants import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    OP_CREATE_CUSTOMER,
    OP_CREATE_PAYMENT_INTENT,
    OP_LIST_CUSTOMERS,
)

RequestSpec = tuple[str, str, dict[str, Any], dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Stripe: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_create_customer(params: dict[str, Any]) -> RequestSpec:
    form: dict[str, Any] = {}
    email = str(params.get("email") or "").strip()
    if email:
        form["email"] = email
    name = str(params.get("name") or "").strip()
    if name:
        form["name"] = name
    description = str(params.get("description") or "").strip()
    if description:
        form["description"] = description
    if not form:
        msg = "Stripe: create_customer requires at least one of email/name/description"
        raise ValueError(msg)
    form.update(_flatten_metadata(params.get("metadata")))
    return "POST", "/v1/customers", form, {}


def _build_list_customers(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {"limit": _coerce_limit(params.get("limit"))}
    email = str(params.get("email") or "").strip()
    if email:
        query["email"] = email
    starting_after = str(params.get("starting_after") or "").strip()
    if starting_after:
        query["starting_after"] = starting_after
    return "GET", "/v1/customers", {}, query


def _build_create_payment_intent(params: dict[str, Any]) -> RequestSpec:
    amount = _coerce_positive_int(params.get("amount"), field="amount")
    currency = str(params.get("currency") or "").strip().lower()
    if not currency:
        msg = "Stripe: create_payment_intent requires 'currency'"
        raise ValueError(msg)
    form: dict[str, Any] = {"amount": str(amount), "currency": currency}
    customer = str(params.get("customer") or "").strip()
    if customer:
        form["customer"] = customer
    description = str(params.get("description") or "").strip()
    if description:
        form["description"] = description
    payment_method_types = params.get("payment_method_types")
    coerced = _coerce_string_list(payment_method_types, field="payment_method_types")
    for index, value in enumerate(coerced):
        form[f"payment_method_types[{index}]"] = value
    form.update(_flatten_metadata(params.get("metadata")))
    return "POST", "/v1/payment_intents", form, {}


def _flatten_metadata(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        msg = "Stripe: 'metadata' must be an object"
        raise ValueError(msg)
    flat: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        flat[f"metadata[{key}]"] = str(value)
    return flat


def _coerce_limit(raw: Any) -> int:
    if raw is None or raw == "":
        return DEFAULT_LIST_LIMIT
    value = _coerce_positive_int(raw, field="limit")
    return min(value, MAX_LIST_LIMIT)


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Stripe: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"Stripe: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


def _coerce_string_list(raw: Any, *, field: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    msg = f"Stripe: {field!r} must be a string or list of strings"
    raise ValueError(msg)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_CREATE_CUSTOMER: _build_create_customer,
    OP_LIST_CUSTOMERS: _build_list_customers,
    OP_CREATE_PAYMENT_INTENT: _build_create_payment_intent,
}
