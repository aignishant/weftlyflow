"""Per-node unit tests for the Phase-6 Tier-1 node additions."""

from __future__ import annotations

import pytest

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.core.datetime_ops_node import DateTimeOpsNode
from weftlyflow.nodes.core.evaluate_expression_node import EvaluateExpressionNode
from weftlyflow.nodes.core.execution_data_node import ExecutionDataNode
from weftlyflow.nodes.core.filter_node import FilterNode
from weftlyflow.nodes.core.merge_node import MergeNode
from weftlyflow.nodes.core.rename_keys_node import RenameKeysNode
from weftlyflow.nodes.core.stop_and_error_node import StopAndErrorNode
from weftlyflow.nodes.core.switch_node import SwitchNode


def _ctx_for(
    node: Node,
    *,
    inputs: dict[str, list[Item]] | None = None,
    mode: str = "manual",
) -> ExecutionContext:
    wf = build_workflow([node], [])
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode=mode,  # type: ignore[arg-type]
        node=node,
        inputs=inputs or {},
    )


# --- Switch -----------------------------------------------------------------


async def test_switch_routes_items_by_case() -> None:
    node = Node(
        id="n1",
        name="route",
        type="weftlyflow.switch",
        parameters={
            "field": "status",
            "cases": [
                {"value": "ok", "port": "case_1"},
                {"value": "warn", "port": "case_2"},
            ],
            "fallback_port": "default",
        },
    )
    items = [
        Item(json={"status": "ok", "id": 1}),
        Item(json={"status": "warn", "id": 2}),
        Item(json={"status": "other", "id": 3}),
    ]
    ctx = _ctx_for(node, inputs={"main": items})
    outputs = await SwitchNode().execute(ctx, items)
    port_names = [p.name for p in SwitchNode.spec.outputs]
    bucketed = dict(zip(port_names, outputs, strict=True))
    assert [it.json["id"] for it in bucketed["case_1"]] == [1]
    assert [it.json["id"] for it in bucketed["case_2"]] == [2]
    assert [it.json["id"] for it in bucketed["default"]] == [3]
    assert bucketed["case_3"] == []


async def test_switch_requires_field() -> None:
    node = Node(
        id="n1", name="r", type="weftlyflow.switch",
        parameters={"field": "", "cases": []},
    )
    with pytest.raises(ValueError, match="field"):
        await SwitchNode().execute(_ctx_for(node), [])


async def test_switch_rejects_unknown_port() -> None:
    node = Node(
        id="n1", name="r", type="weftlyflow.switch",
        parameters={
            "field": "status",
            "cases": [{"value": "ok", "port": "case_99"}],
            "fallback_port": "default",
        },
    )
    items = [Item(json={"status": "ok"})]
    with pytest.raises(ValueError, match="unknown port"):
        await SwitchNode().execute(_ctx_for(node, inputs={"main": items}), items)


# --- Filter -----------------------------------------------------------------


async def test_filter_keeps_items_matching_predicate() -> None:
    node = Node(
        id="n1", name="f", type="weftlyflow.filter",
        parameters={"field": "age", "operator": "greater_than", "value": 18},
    )
    items = [Item(json={"age": 10}), Item(json={"age": 30}), Item(json={"age": 21})]
    out = await FilterNode().execute(_ctx_for(node, inputs={"main": items}), items)
    kept = [it.json["age"] for it in out[0]]
    assert kept == [30, 21]


async def test_filter_expression_path_wins_over_predicate() -> None:
    node = Node(
        id="n1", name="f", type="weftlyflow.filter",
        parameters={
            "expression": "{{ $json.age >= 18 }}",
            "field": "age",
            "operator": "less_than",
            "value": 5,
        },
    )
    items = [Item(json={"age": 1}), Item(json={"age": 25})]
    out = await FilterNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert [it.json["age"] for it in out[0]] == [25]


async def test_filter_requires_field_or_expression() -> None:
    node = Node(id="n1", name="f", type="weftlyflow.filter", parameters={})
    with pytest.raises(ValueError):
        await FilterNode().execute(_ctx_for(node), [])


# --- Merge ------------------------------------------------------------------


async def test_merge_append_concatenates_inputs() -> None:
    node = Node(id="n1", name="m", type="weftlyflow.merge", parameters={"mode": "append"})
    a = [Item(json={"src": "a", "i": 0}), Item(json={"src": "a", "i": 1})]
    b = [Item(json={"src": "b", "i": 0})]
    ctx = _ctx_for(node, inputs={"main": a, "input_2": b})
    out = await MergeNode().execute(ctx, a)
    assert [it.json["src"] for it in out[0]] == ["a", "a", "b"]


async def test_merge_by_position_zips_items() -> None:
    node = Node(
        id="n1", name="m", type="weftlyflow.merge",
        parameters={"mode": "combine_by_position"},
    )
    a = [Item(json={"id": 1}), Item(json={"id": 2}), Item(json={"id": 3})]
    b = [Item(json={"name": "a"}), Item(json={"name": "b"})]
    ctx = _ctx_for(node, inputs={"main": a, "input_2": b})
    out = await MergeNode().execute(ctx, a)
    assert [it.json for it in out[0]] == [
        {"id": 1, "name": "a"},
        {"id": 2, "name": "b"},
    ]


async def test_merge_by_key_joins_on_shared_field() -> None:
    node = Node(
        id="n1", name="m", type="weftlyflow.merge",
        parameters={"mode": "combine_by_key", "key": "id"},
    )
    a = [Item(json={"id": 1, "x": "a1"}), Item(json={"id": 2, "x": "a2"})]
    b = [Item(json={"id": 2, "y": "b2"}), Item(json={"id": 3, "y": "b3"})]
    ctx = _ctx_for(node, inputs={"main": a, "input_2": b})
    out = await MergeNode().execute(ctx, a)
    assert [it.json for it in out[0]] == [{"id": 2, "x": "a2", "y": "b2"}]


async def test_merge_by_key_requires_key_param() -> None:
    node = Node(
        id="n1", name="m", type="weftlyflow.merge",
        parameters={"mode": "combine_by_key", "key": ""},
    )
    with pytest.raises(ValueError, match="key"):
        await MergeNode().execute(
            _ctx_for(node, inputs={"main": [], "input_2": []}), [],
        )


# --- Rename Keys ------------------------------------------------------------


async def test_rename_keys_moves_values_between_paths() -> None:
    node = Node(
        id="n1", name="r", type="weftlyflow.rename_keys",
        parameters={
            "mappings": [{"from": "user.firstName", "to": "user.first_name"}],
            "drop_missing": True,
        },
    )
    items = [Item(json={"user": {"firstName": "Ada", "lastName": "Lovelace"}})]
    out = await RenameKeysNode().execute(_ctx_for(node, inputs={"main": items}), items)
    [result] = out[0]
    assert result.json == {"user": {"first_name": "Ada", "lastName": "Lovelace"}}


async def test_rename_keys_respects_drop_missing_false() -> None:
    node = Node(
        id="n1", name="r", type="weftlyflow.rename_keys",
        parameters={
            "mappings": [{"from": "nonexistent", "to": "x"}],
            "drop_missing": False,
        },
    )
    items = [Item(json={"existing": 1})]
    with pytest.raises(KeyError):
        await RenameKeysNode().execute(_ctx_for(node, inputs={"main": items}), items)


async def test_rename_keys_is_no_op_without_mappings() -> None:
    node = Node(
        id="n1", name="r", type="weftlyflow.rename_keys",
        parameters={"mappings": [], "drop_missing": True},
    )
    items = [Item(json={"a": 1})]
    out = await RenameKeysNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert [it.json for it in out[0]] == [{"a": 1}]


# --- DateTime Ops -----------------------------------------------------------


async def test_datetime_ops_now_emits_iso_string() -> None:
    node = Node(id="n1", name="d", type="weftlyflow.datetime_ops", parameters={})
    out = await DateTimeOpsNode().execute(_ctx_for(node, inputs={"main": [Item()]}), [Item()])
    value = out[0][0].json["at"]
    assert isinstance(value, str)
    assert "T" in value


async def test_datetime_ops_add_days() -> None:
    node = Node(
        id="n1", name="d", type="weftlyflow.datetime_ops",
        parameters={
            "operation": "add",
            "source": "when",
            "unit": "days",
            "amount": 2,
            "output_field": "later",
        },
    )
    items = [Item(json={"when": "2026-04-22T00:00:00+00:00"})]
    out = await DateTimeOpsNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert out[0][0].json["later"].startswith("2026-04-24T00:00:00")


async def test_datetime_ops_diff_seconds() -> None:
    node = Node(
        id="n1", name="d", type="weftlyflow.datetime_ops",
        parameters={
            "operation": "diff_seconds",
            "source": "end",
            "source_b": "start",
            "output_field": "seconds",
        },
    )
    items = [
        Item(
            json={
                "start": "2026-04-22T00:00:00+00:00",
                "end": "2026-04-22T00:01:30+00:00",
            },
        ),
    ]
    out = await DateTimeOpsNode().execute(_ctx_for(node, inputs={"main": items}), items)
    assert out[0][0].json["seconds"] == 90.0


async def test_datetime_ops_rejects_unknown_operation() -> None:
    node = Node(
        id="n1", name="d", type="weftlyflow.datetime_ops",
        parameters={"operation": "nope"},
    )
    with pytest.raises(ValueError, match="unknown operation"):
        await DateTimeOpsNode().execute(_ctx_for(node, inputs={"main": [Item()]}), [Item()])


# --- Evaluate Expression ----------------------------------------------------


async def test_evaluate_expression_writes_result_per_item() -> None:
    node = Node(
        id="n1", name="e", type="weftlyflow.evaluate_expression",
        parameters={"expression": "{{ $json.price * 2 }}", "output_field": "doubled"},
    )
    items = [Item(json={"price": 5}), Item(json={"price": 10})]
    out = await EvaluateExpressionNode().execute(
        _ctx_for(node, inputs={"main": items}), items,
    )
    assert [it.json["doubled"] for it in out[0]] == [10, 20]


async def test_evaluate_expression_requires_template() -> None:
    node = Node(
        id="n1", name="e", type="weftlyflow.evaluate_expression",
        parameters={"expression": ""},
    )
    with pytest.raises(ValueError):
        await EvaluateExpressionNode().execute(
            _ctx_for(node, inputs={"main": [Item()]}), [Item()],
        )


# --- Stop & Error -----------------------------------------------------------


async def test_stop_and_error_raises_resolved_message() -> None:
    node = Node(
        id="n1", name="s", type="weftlyflow.stop_and_error",
        parameters={"message": "boom on id={{ $json.id }}", "code": "bad"},
    )
    items = [Item(json={"id": 42})]
    with pytest.raises(NodeExecutionError, match="boom on id=42"):
        await StopAndErrorNode().execute(
            _ctx_for(node, inputs={"main": items}), items,
        )


# --- Execution Data ---------------------------------------------------------


async def test_execution_data_merges_metadata_under_prefix() -> None:
    node = Node(
        id="n1", name="x", type="weftlyflow.execution_data",
        parameters={"prefix": "_execution"},
    )
    items = [Item(json={"existing": 1})]
    out = await ExecutionDataNode().execute(
        _ctx_for(node, inputs={"main": items}), items,
    )
    payload = out[0][0].json
    assert payload["existing"] == 1
    assert payload["_execution"]["execution_id"] == "ex_test"
    assert payload["_execution"]["mode"] == "manual"


async def test_execution_data_merges_at_top_level_when_prefix_empty() -> None:
    node = Node(
        id="n1", name="x", type="weftlyflow.execution_data",
        parameters={"prefix": ""},
    )
    items = [Item(json={})]
    out = await ExecutionDataNode().execute(
        _ctx_for(node, inputs={"main": items}), items,
    )
    assert out[0][0].json["execution_id"] == "ex_test"
