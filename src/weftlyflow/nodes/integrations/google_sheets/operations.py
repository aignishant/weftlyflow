"""Per-operation request builders for the Google Sheets node.

Each builder returns ``(http_method, path, json_body, query_params)``.
The path is assembled with ``urllib.parse.quote`` so sheet names containing
spaces (``'Sheet 1'!A1:B2``) survive URL encoding intact.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.google_sheets.constants import (
    OP_APPEND_ROW,
    OP_READ_RANGE,
    OP_UPDATE_RANGE,
    VALID_VALUE_INPUT_OPTIONS,
    VALUE_INPUT_USER_ENTERED,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Google Sheets: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_read_range(params: dict[str, Any]) -> RequestSpec:
    spreadsheet_id = _required(params, "spreadsheet_id")
    cell_range = _required(params, "range")
    path = f"/v4/spreadsheets/{quote(spreadsheet_id, safe='')}/values/{quote(cell_range, safe='')}"
    return "GET", path, None, {}


def _build_append_row(params: dict[str, Any]) -> RequestSpec:
    spreadsheet_id = _required(params, "spreadsheet_id")
    cell_range = _required(params, "range")
    values = _coerce_values(params.get("values"))
    value_input_option = _coerce_value_input(params.get("value_input_option"))
    path = (
        f"/v4/spreadsheets/{quote(spreadsheet_id, safe='')}"
        f"/values/{quote(cell_range, safe='')}:append"
    )
    body: dict[str, Any] = {"range": cell_range, "majorDimension": "ROWS", "values": values}
    query = {"valueInputOption": value_input_option}
    return "POST", path, body, query


def _build_update_range(params: dict[str, Any]) -> RequestSpec:
    spreadsheet_id = _required(params, "spreadsheet_id")
    cell_range = _required(params, "range")
    values = _coerce_values(params.get("values"))
    value_input_option = _coerce_value_input(params.get("value_input_option"))
    path = (
        f"/v4/spreadsheets/{quote(spreadsheet_id, safe='')}"
        f"/values/{quote(cell_range, safe='')}"
    )
    body: dict[str, Any] = {"range": cell_range, "majorDimension": "ROWS", "values": values}
    query = {"valueInputOption": value_input_option}
    return "PUT", path, body, query


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Google Sheets: {key!r} is required"
        raise ValueError(msg)
    return value


def _coerce_values(raw: Any) -> list[list[Any]]:
    if raw is None or raw == "":
        msg = "Google Sheets: 'values' is required (list of rows)"
        raise ValueError(msg)
    if not isinstance(raw, list):
        msg = "Google Sheets: 'values' must be a list of rows"
        raise ValueError(msg)
    rows: list[list[Any]] = []
    for row in raw:
        if isinstance(row, list):
            rows.append(list(row))
        else:
            rows.append([row])
    if not rows:
        msg = "Google Sheets: 'values' must contain at least one row"
        raise ValueError(msg)
    return rows


def _coerce_value_input(raw: Any) -> str:
    if raw is None or raw == "":
        return VALUE_INPUT_USER_ENTERED
    value = str(raw).strip().upper()
    if value not in VALID_VALUE_INPUT_OPTIONS:
        msg = (
            f"Google Sheets: invalid value_input_option {value!r} — must be "
            f"one of {sorted(VALID_VALUE_INPUT_OPTIONS)}"
        )
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_READ_RANGE: _build_read_range,
    OP_APPEND_ROW: _build_append_row,
    OP_UPDATE_RANGE: _build_update_range,
}
