"""Unit tests for the ``guard_schema_enforce`` node and its validator.

Validator tests exercise each supported keyword in isolation; node
tests cover the field selector, strict vs non-strict modes, and the
shape of the error payload surfaced to downstream nodes.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.ai.guard_schema_enforce import GuardSchemaEnforceNode
from weftlyflow.nodes.ai.guard_schema_enforce.validator import validate


def _ctx_for(
    node: Node,
    *,
    static_data: dict[str, Any] | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [])
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": []},
        static_data=static_data if static_data is not None else {},
    )


# --- validator -------------------------------------------------------


def test_validate_matching_object_returns_no_errors() -> None:
    schema = {
        "type": "object",
        "required": ["name", "age"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "age": {"type": "integer", "minimum": 0},
        },
    }
    assert validate({"name": "alice", "age": 30}, schema) == []


def test_validate_type_mismatch_reports_root() -> None:
    errors = validate("nope", {"type": "object"})
    assert errors == [("", "expected type 'object', got string")]


def test_validate_missing_required_property() -> None:
    schema = {
        "type": "object",
        "required": ["email"],
        "properties": {"email": {"type": "string"}},
    }
    assert validate({}, schema) == [("", "missing required property 'email'")]


def test_validate_additional_properties_rejected_when_false() -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "additionalProperties": False,
    }
    errors = validate({"name": "a", "extra": 1}, schema)
    assert errors == [("", "unexpected property 'extra'")]


def test_validate_nested_property_error_path() -> None:
    schema = {
        "type": "object",
        "properties": {"user": {"type": "object", "required": ["id"]}},
    }
    errors = validate({"user": {}}, schema)
    assert errors == [("/user", "missing required property 'id'")]


def test_validate_array_items_schema_applied_per_element() -> None:
    schema = {"type": "array", "items": {"type": "integer"}}
    errors = validate([1, "bad", 3], schema)
    assert errors == [("/1", "expected type 'integer', got string")]


def test_validate_enum_rejects_non_member() -> None:
    errors = validate("red", {"enum": ["green", "blue"]})
    assert errors == [("", "value 'red' is not one of ['green', 'blue']")]


def test_validate_string_length_bounds() -> None:
    errors = validate("ab", {"type": "string", "minLength": 3})
    assert errors == [("", "string length 2 < minLength 3")]


def test_validate_string_pattern_mismatch() -> None:
    errors = validate("abc", {"type": "string", "pattern": r"^\d+$"})
    assert errors == [("", "string does not match pattern '^\\\\d+$'")]


def test_validate_numeric_bounds() -> None:
    errors = validate(100, {"type": "integer", "maximum": 50})
    assert errors == [("", "value 100 > maximum 50")]


def test_validate_array_length_bounds() -> None:
    errors = validate([1], {"type": "array", "minItems": 2})
    assert errors == [("", "array length 1 < minItems 2")]


def test_validate_boolean_is_not_integer_for_type_check() -> None:
    errors = validate(True, {"type": "integer"})
    assert errors == [("", "expected type 'integer', got boolean")]


def test_validate_number_accepts_integer() -> None:
    assert validate(5, {"type": "number"}) == []


def test_validate_union_type_list() -> None:
    schema = {"type": ["string", "null"]}
    assert validate(None, schema) == []
    assert validate("x", schema) == []
    assert validate(1, schema) == [("", "expected type ['string', 'null'], got integer")]


# --- node ------------------------------------------------------------


async def test_node_validates_whole_item_by_default() -> None:
    schema = {"type": "object", "required": ["x"]}
    node = Node(
        id="g", name="g", type="weftlyflow.guard_schema_enforce",
        parameters={"schema": schema},
    )
    item = Item(json={"x": 1})
    out = await GuardSchemaEnforceNode().execute(_ctx_for(node), [item])
    payload = out[0][0].json
    assert payload["schema_valid"] is True
    assert payload["schema_errors"] == []


async def test_node_reports_errors_with_path_and_message() -> None:
    schema = {"type": "object", "required": ["email"]}
    node = Node(
        id="g", name="g", type="weftlyflow.guard_schema_enforce",
        parameters={"schema": schema},
    )
    item = Item(json={})
    out = await GuardSchemaEnforceNode().execute(_ctx_for(node), [item])
    payload = out[0][0].json
    assert payload["schema_valid"] is False
    assert payload["schema_errors"] == [
        {"path": "/", "message": "missing required property 'email'"},
    ]


async def test_node_validates_sub_field_when_specified() -> None:
    schema = {"type": "string", "minLength": 3}
    node = Node(
        id="g", name="g", type="weftlyflow.guard_schema_enforce",
        parameters={"field": "name", "schema": schema},
    )
    item = Item(json={"name": "ab", "other": 1})
    out = await GuardSchemaEnforceNode().execute(_ctx_for(node), [item])
    payload = out[0][0].json
    assert payload["schema_valid"] is False
    assert payload["schema_errors"][0]["message"] == "string length 2 < minLength 3"


async def test_node_strict_mode_raises_on_invalid() -> None:
    schema = {"type": "object", "required": ["x"]}
    node = Node(
        id="g", name="g", type="weftlyflow.guard_schema_enforce",
        parameters={"schema": schema, "strict": True},
    )
    item = Item(json={})
    with pytest.raises(NodeExecutionError, match="validation failed"):
        await GuardSchemaEnforceNode().execute(_ctx_for(node), [item])


async def test_node_strict_mode_passes_through_valid_items() -> None:
    schema = {"type": "object", "required": ["x"]}
    node = Node(
        id="g", name="g", type="weftlyflow.guard_schema_enforce",
        parameters={"schema": schema, "strict": True},
    )
    item = Item(json={"x": 1})
    out = await GuardSchemaEnforceNode().execute(_ctx_for(node), [item])
    assert out[0][0].json["schema_valid"] is True


async def test_node_rejects_non_dict_schema() -> None:
    node = Node(
        id="g", name="g", type="weftlyflow.guard_schema_enforce",
        parameters={"schema": "not-an-object"},
    )
    item = Item(json={})
    with pytest.raises(NodeExecutionError, match="must be a JSON object"):
        await GuardSchemaEnforceNode().execute(_ctx_for(node), [item])


async def test_node_preserves_other_fields() -> None:
    schema = {"type": "object"}
    node = Node(
        id="g", name="g", type="weftlyflow.guard_schema_enforce",
        parameters={"schema": schema},
    )
    item = Item(json={"keep": "me", "also": 7})
    out = await GuardSchemaEnforceNode().execute(_ctx_for(node), [item])
    payload = out[0][0].json
    assert payload["keep"] == "me" and payload["also"] == 7


async def test_node_strict_string_true_is_honoured() -> None:
    """'strict' passed as the string 'true' (typical form-encoded UI) works."""
    schema = {"type": "object", "required": ["x"]}
    node = Node(
        id="g", name="g", type="weftlyflow.guard_schema_enforce",
        parameters={"schema": schema, "strict": "true"},
    )
    item = Item(json={})
    with pytest.raises(NodeExecutionError, match="validation failed"):
        await GuardSchemaEnforceNode().execute(_ctx_for(node), [item])
