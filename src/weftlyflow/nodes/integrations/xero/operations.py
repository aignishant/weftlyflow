"""Per-operation request builders for the Xero node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to the Accounting API root (``/api.xro/2.0``).

Distinctive Xero shape:

* Create/update endpoints for invoices accept a collection wrapper —
  ``{"Invoices": [{...}]}``. The builder wraps a single ``document``
  dict into that shape for ergonomic node authoring.
* POST is used for *both* create and update on ``/Invoices/{id}`` —
  the invoice id in the path is the discriminator.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.xero.constants import (
    MAX_PAGE_SIZE,
    OP_CREATE_INVOICE,
    OP_GET_INVOICE,
    OP_LIST_ACCOUNTS,
    OP_LIST_CONTACTS,
    OP_LIST_INVOICES,
    OP_UPDATE_INVOICE,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Xero: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_list_invoices(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {}
    _maybe_add(query, "where", params.get("where"))
    _maybe_add(query, "order", params.get("order"))
    _maybe_add(query, "Statuses", params.get("statuses"))
    page = params.get("page")
    if page is not None and page != "":
        query["page"] = _coerce_positive_int(page, field="page")
    page_size = params.get("page_size")
    if page_size is not None and page_size != "":
        query["pageSize"] = min(
            _coerce_positive_int(page_size, field="page_size"),
            MAX_PAGE_SIZE,
        )
    return "GET", "/Invoices", None, query


def _build_get_invoice(params: dict[str, Any]) -> RequestSpec:
    invoice_id = _required(params, "invoice_id")
    return "GET", f"/Invoices/{quote(invoice_id, safe='')}", None, {}


def _build_create_invoice(params: dict[str, Any]) -> RequestSpec:
    document = _coerce_document(params.get("document"))
    body = {"Invoices": [document]}
    return "POST", "/Invoices", body, {}


def _build_update_invoice(params: dict[str, Any]) -> RequestSpec:
    invoice_id = _required(params, "invoice_id")
    document = _coerce_document(params.get("document"))
    body = {"Invoices": [document]}
    return "POST", f"/Invoices/{quote(invoice_id, safe='')}", body, {}


def _build_list_contacts(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {}
    _maybe_add(query, "where", params.get("where"))
    _maybe_add(query, "order", params.get("order"))
    _maybe_add(query, "IDs", params.get("ids"))
    page = params.get("page")
    if page is not None and page != "":
        query["page"] = _coerce_positive_int(page, field="page")
    return "GET", "/Contacts", None, query


def _build_list_accounts(params: dict[str, Any]) -> RequestSpec:
    query: dict[str, Any] = {}
    _maybe_add(query, "where", params.get("where"))
    _maybe_add(query, "order", params.get("order"))
    return "GET", "/Accounts", None, query


def _coerce_document(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        msg = "Xero: 'document' is required"
        raise ValueError(msg)
    if not isinstance(raw, dict):
        msg = "Xero: 'document' must be a JSON object"
        raise ValueError(msg)
    return raw


def _maybe_add(query: dict[str, Any], key: str, raw: Any) -> None:
    if raw is None:
        return
    value = str(raw).strip() if not isinstance(raw, (list, tuple)) else ""
    if isinstance(raw, (list, tuple)):
        if not raw:
            return
        query[key] = ",".join(str(v) for v in raw)
        return
    if value:
        query[key] = value


def _coerce_positive_int(raw: Any, *, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Xero: {field!r} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"Xero: {field!r} must be >= 1"
        raise ValueError(msg)
    return value


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Xero: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LIST_INVOICES: _build_list_invoices,
    OP_GET_INVOICE: _build_get_invoice,
    OP_CREATE_INVOICE: _build_create_invoice,
    OP_UPDATE_INVOICE: _build_update_invoice,
    OP_LIST_CONTACTS: _build_list_contacts,
    OP_LIST_ACCOUNTS: _build_list_accounts,
}
