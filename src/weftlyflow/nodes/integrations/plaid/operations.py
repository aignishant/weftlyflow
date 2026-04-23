"""Per-operation request builders for the Plaid node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to the environment host chosen by the node.

Plaid does not use URL-variable paths; operation scope is carried
inside the JSON body (e.g. ``access_token``, ``item_id``,
``transaction_cursor``). The builders here return the body **without**
``client_id`` / ``secret`` — those are folded in by the node so a
single credential row can serve every operation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.plaid.constants import (
    OP_ACCOUNTS_GET,
    OP_ITEM_GET,
    OP_LINK_TOKEN_CREATE,
    OP_TRANSACTIONS_SYNC,
)

RequestSpec = tuple[str, str, dict[str, Any], dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Plaid: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_link_token_create(params: dict[str, Any]) -> RequestSpec:
    client_user_id = _required_str(params, "client_user_id")
    products = params.get("products")
    if not isinstance(products, list) or not products:
        msg = "Plaid: 'products' must be a non-empty list for link_token_create"
        raise ValueError(msg)
    country_codes = params.get("country_codes")
    if not isinstance(country_codes, list) or not country_codes:
        msg = "Plaid: 'country_codes' must be a non-empty list for link_token_create"
        raise ValueError(msg)
    language = str(params.get("language") or "en").strip() or "en"
    body: dict[str, Any] = {
        "client_name": _required_str(params, "client_name"),
        "user": {"client_user_id": client_user_id},
        "products": [str(p) for p in products],
        "country_codes": [str(c) for c in country_codes],
        "language": language,
    }
    webhook = str(params.get("webhook") or "").strip()
    if webhook:
        body["webhook"] = webhook
    return "POST", "/link/token/create", body, {}


def _build_item_get(params: dict[str, Any]) -> RequestSpec:
    body = {"access_token": _required_str(params, "access_token")}
    return "POST", "/item/get", body, {}


def _build_accounts_get(params: dict[str, Any]) -> RequestSpec:
    body: dict[str, Any] = {"access_token": _required_str(params, "access_token")}
    account_ids = params.get("account_ids")
    if isinstance(account_ids, list) and account_ids:
        body["options"] = {"account_ids": [str(a) for a in account_ids]}
    return "POST", "/accounts/get", body, {}


def _build_transactions_sync(params: dict[str, Any]) -> RequestSpec:
    body: dict[str, Any] = {
        "access_token": _required_str(params, "access_token"),
    }
    cursor = params.get("cursor")
    if isinstance(cursor, str) and cursor.strip():
        body["cursor"] = cursor.strip()
    count = params.get("count")
    if isinstance(count, int) and count > 0:
        body["count"] = count
    return "POST", "/transactions/sync", body, {}


def _required_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Plaid: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_LINK_TOKEN_CREATE: _build_link_token_create,
    OP_ITEM_GET: _build_item_get,
    OP_ACCOUNTS_GET: _build_accounts_get,
    OP_TRANSACTIONS_SYNC: _build_transactions_sync,
}
