"""Per-operation request builders for the QuickBooks Online node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``/v3/company/{realmId}`` — the realmId is *not* included
here; the node prefixes it because realmId is owned by the credential.

Distinctive QuickBooks shape:

* ``query`` operation posts a SQL-ish select via the
  ``/query?query=...`` endpoint — the SQL goes in the *query string*
  with an explicit ``application/text`` content type, not a JSON body.
* Resource creates POST naked JSON ``{...}`` — there is no
  ``{"Invoice": {...}}`` envelope wrapping (unlike Xero).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.quickbooks.constants import (
    OP_CREATE_CUSTOMER,
    OP_CREATE_INVOICE,
    OP_GET_CUSTOMER,
    OP_GET_INVOICE,
    OP_QUERY,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"QuickBooks: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_query(params: dict[str, Any]) -> RequestSpec:
    sql = _required(params, "query")
    return "GET", "/query", None, {"query": sql}


def _build_get_invoice(params: dict[str, Any]) -> RequestSpec:
    invoice_id = _required(params, "invoice_id")
    return "GET", f"/invoice/{quote(invoice_id, safe='')}", None, {}


def _build_create_invoice(params: dict[str, Any]) -> RequestSpec:
    document = _coerce_document(params.get("document"))
    return "POST", "/invoice", document, {}


def _build_get_customer(params: dict[str, Any]) -> RequestSpec:
    customer_id = _required(params, "customer_id")
    return "GET", f"/customer/{quote(customer_id, safe='')}", None, {}


def _build_create_customer(params: dict[str, Any]) -> RequestSpec:
    document = _coerce_document(params.get("document"))
    return "POST", "/customer", document, {}


def _coerce_document(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        msg = "QuickBooks: 'document' is required"
        raise ValueError(msg)
    if not isinstance(raw, dict):
        msg = "QuickBooks: 'document' must be a JSON object"
        raise ValueError(msg)
    return raw


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"QuickBooks: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_QUERY: _build_query,
    OP_GET_INVOICE: _build_get_invoice,
    OP_CREATE_INVOICE: _build_create_invoice,
    OP_GET_CUSTOMER: _build_get_customer,
    OP_CREATE_CUSTOMER: _build_create_customer,
}
