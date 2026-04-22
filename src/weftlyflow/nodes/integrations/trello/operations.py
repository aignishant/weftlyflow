"""Per-operation request builders for the Trello node.

Each builder returns ``(http_method, path, query_params)``. Trello's
authentication (key + token as query parameters) is handled by the
credential type's ``inject()`` — builders return only *operation-level*
query params.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.trello.constants import (
    API_VERSION_PREFIX,
    OP_CREATE_CARD,
    OP_DELETE_CARD,
    OP_GET_BOARD,
    OP_GET_CARD,
    OP_LIST_CARDS,
    OP_UPDATE_CARD,
)

RequestSpec = tuple[str, str, dict[str, Any]]

_CARD_UPDATE_FIELDS: frozenset[str] = frozenset(
    {"name", "desc", "closed", "idList", "idBoard", "due", "dueComplete", "pos"},
)
_CARD_CREATE_OPTIONAL_FIELDS: frozenset[str] = frozenset(
    {"desc", "due", "pos", "urlSource", "idMembers", "idLabels"},
)


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Trello: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_get_board(params: dict[str, Any]) -> RequestSpec:
    board_id = _required(params, "board_id")
    return "GET", f"{API_VERSION_PREFIX}/boards/{quote(board_id, safe='')}", {}


def _build_list_cards(params: dict[str, Any]) -> RequestSpec:
    board_id = _required(params, "board_id")
    query: dict[str, Any] = {}
    filter_value = str(params.get("filter") or "").strip()
    if filter_value:
        query["filter"] = filter_value
    return (
        "GET",
        f"{API_VERSION_PREFIX}/boards/{quote(board_id, safe='')}/cards",
        query,
    )


def _build_get_card(params: dict[str, Any]) -> RequestSpec:
    card_id = _required(params, "card_id")
    return "GET", f"{API_VERSION_PREFIX}/cards/{quote(card_id, safe='')}", {}


def _build_create_card(params: dict[str, Any]) -> RequestSpec:
    list_id = _required(params, "list_id")
    name = _required(params, "name")
    query: dict[str, Any] = {"idList": list_id, "name": name}
    extras = params.get("extra_fields")
    if extras is not None:
        if not isinstance(extras, dict):
            msg = "Trello: 'extra_fields' must be a JSON object"
            raise ValueError(msg)
        for key, value in extras.items():
            if key in _CARD_CREATE_OPTIONAL_FIELDS:
                query[key] = _stringify(value)
    return "POST", f"{API_VERSION_PREFIX}/cards", query


def _build_update_card(params: dict[str, Any]) -> RequestSpec:
    card_id = _required(params, "card_id")
    updates = params.get("fields")
    if not isinstance(updates, dict) or not updates:
        msg = "Trello: 'fields' must be a non-empty JSON object"
        raise ValueError(msg)
    query: dict[str, Any] = {}
    for key, value in updates.items():
        if key not in _CARD_UPDATE_FIELDS:
            msg = f"Trello: unknown card field {key!r}"
            raise ValueError(msg)
        query[key] = _stringify(value)
    return "PUT", f"{API_VERSION_PREFIX}/cards/{quote(card_id, safe='')}", query


def _build_delete_card(params: dict[str, Any]) -> RequestSpec:
    card_id = _required(params, "card_id")
    return "DELETE", f"{API_VERSION_PREFIX}/cards/{quote(card_id, safe='')}", {}


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Trello: {key!r} is required"
        raise ValueError(msg)
    return value


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(_stringify(v) for v in value)
    return str(value)


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GET_BOARD: _build_get_board,
    OP_LIST_CARDS: _build_list_cards,
    OP_GET_CARD: _build_get_card,
    OP_CREATE_CARD: _build_create_card,
    OP_UPDATE_CARD: _build_update_card,
    OP_DELETE_CARD: _build_delete_card,
}
