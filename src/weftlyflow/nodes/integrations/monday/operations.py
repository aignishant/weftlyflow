"""Per-operation GraphQL query builders for the Monday.com node.

Each builder returns ``(query, variables)``. The node layer packs these
into the POST body ``{"query": query, "variables": variables}`` that
Monday.com's single ``/v2`` endpoint expects.

Column values are sent as a JSON-encoded string — Monday's GraphQL
schema declares ``column_values`` as ``JSON!`` (i.e. a string containing
JSON), so the node serialises the user-supplied object here.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from weftlyflow.nodes.integrations.monday.constants import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    OP_CHANGE_COLUMN_VALUES,
    OP_CREATE_ITEM,
    OP_CREATE_UPDATE,
    OP_GET_BOARD,
    OP_GET_BOARDS,
    OP_GET_ITEMS,
)

GraphQLSpec = tuple[str, dict[str, Any]]

_GET_BOARDS_QUERY: str = (
    "query ($limit: Int!) { "
    "boards(limit: $limit) { id name state board_kind } "
    "}"
)
_GET_BOARD_QUERY: str = (
    "query ($id: [ID!]) { "
    "boards(ids: $id) { id name state description "
    "columns { id title type } } "
    "}"
)
_GET_ITEMS_QUERY: str = (
    "query ($board_id: ID!, $limit: Int!) { "
    "boards(ids: [$board_id]) { "
    "items_page(limit: $limit) { "
    "cursor items { id name column_values { id text value } } "
    "} } }"
)
_CREATE_ITEM_MUTATION: str = (
    "mutation ($board_id: ID!, $item_name: String!, $column_values: JSON, $group_id: String) { "
    "create_item(board_id: $board_id, item_name: $item_name, "
    "column_values: $column_values, group_id: $group_id) { id name } "
    "}"
)
_CHANGE_COLUMN_VALUES_MUTATION: str = (
    "mutation ($board_id: ID!, $item_id: ID!, $column_values: JSON!) { "
    "change_multiple_column_values(board_id: $board_id, item_id: $item_id, "
    "column_values: $column_values) { id } "
    "}"
)
_CREATE_UPDATE_MUTATION: str = (
    "mutation ($item_id: ID!, $body: String!) { "
    "create_update(item_id: $item_id, body: $body) { id body } "
    "}"
)


def build_request(operation: str, params: dict[str, Any]) -> GraphQLSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Monday: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_get_boards(params: dict[str, Any]) -> GraphQLSpec:
    limit = _coerce_limit(params.get("limit"))
    return _GET_BOARDS_QUERY, {"limit": limit}


def _build_get_board(params: dict[str, Any]) -> GraphQLSpec:
    board_id = _required(params, "board_id")
    return _GET_BOARD_QUERY, {"id": [board_id]}


def _build_get_items(params: dict[str, Any]) -> GraphQLSpec:
    board_id = _required(params, "board_id")
    limit = _coerce_limit(params.get("limit"))
    return _GET_ITEMS_QUERY, {"board_id": board_id, "limit": limit}


def _build_create_item(params: dict[str, Any]) -> GraphQLSpec:
    board_id = _required(params, "board_id")
    item_name = _required(params, "item_name")
    column_values = params.get("column_values")
    encoded_columns: str | None = None
    if column_values not in (None, ""):
        if not isinstance(column_values, dict):
            msg = "Monday: 'column_values' must be a JSON object"
            raise ValueError(msg)
        encoded_columns = json.dumps(column_values)
    variables: dict[str, Any] = {
        "board_id": board_id,
        "item_name": item_name,
        "column_values": encoded_columns,
    }
    group_id = str(params.get("group_id") or "").strip()
    variables["group_id"] = group_id or None
    return _CREATE_ITEM_MUTATION, variables


def _build_change_column_values(params: dict[str, Any]) -> GraphQLSpec:
    board_id = _required(params, "board_id")
    item_id = _required(params, "item_id")
    column_values = params.get("column_values")
    if not isinstance(column_values, dict) or not column_values:
        msg = "Monday: 'column_values' must be a non-empty JSON object"
        raise ValueError(msg)
    return (
        _CHANGE_COLUMN_VALUES_MUTATION,
        {
            "board_id": board_id,
            "item_id": item_id,
            "column_values": json.dumps(column_values),
        },
    )


def _build_create_update(params: dict[str, Any]) -> GraphQLSpec:
    item_id = _required(params, "item_id")
    body = str(params.get("body") or "")
    if not body.strip():
        msg = "Monday: 'body' is required for create_update"
        raise ValueError(msg)
    return _CREATE_UPDATE_MUTATION, {"item_id": item_id, "body": body}


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Monday: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_limit(raw: Any) -> int:
    if raw in (None, ""):
        return DEFAULT_PAGE_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = "Monday: 'limit' must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Monday: 'limit' must be >= 1"
        raise ValueError(msg)
    return min(value, MAX_PAGE_LIMIT)


_Builder = Callable[[dict[str, Any]], GraphQLSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_GET_BOARDS: _build_get_boards,
    OP_GET_BOARD: _build_get_board,
    OP_GET_ITEMS: _build_get_items,
    OP_CREATE_ITEM: _build_create_item,
    OP_CHANGE_COLUMN_VALUES: _build_change_column_values,
    OP_CREATE_UPDATE: _build_create_update,
}
