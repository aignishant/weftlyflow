"""Unit tests for the Phase-3 trigger nodes."""

from __future__ import annotations

from tests.unit.engine.conftest import build_workflow
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.core.schedule_trigger import ScheduleTriggerNode
from weftlyflow.nodes.core.webhook_trigger import WebhookTriggerNode


def _ctx_for(node: Node, inputs: list[Item] | None = None) -> ExecutionContext:
    wf = build_workflow([node], [])
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="webhook",
        node=node,
        inputs={"main": list(inputs or [])},
    )


async def test_webhook_trigger_flattens_request_payload() -> None:
    node = Node(id="node_1", name="Webhook", type="weftlyflow.webhook_trigger")
    seeded = Item(
        json={
            "node_id": "node_1",
            "request": {
                "method": "POST",
                "path": "demo/hook",
                "headers": {"content-type": "application/json"},
                "query": {"q": "hi"},
                "query_all": {"q": ["hi"]},
                "body": {"greet": "world"},
            },
        },
    )
    out = await WebhookTriggerNode().execute(_ctx_for(node, [seeded]), [seeded])
    [flattened] = out[0]
    assert flattened.json == {
        "method": "POST",
        "path": "demo/hook",
        "headers": {"content-type": "application/json"},
        "query": {"q": "hi"},
        "query_all": {"q": ["hi"]},
        "body": {"greet": "world"},
    }


async def test_webhook_trigger_passes_through_non_request_items() -> None:
    node = Node(id="node_1", name="Webhook", type="weftlyflow.webhook_trigger")
    plain = Item(json={"some": "payload"})
    out = await WebhookTriggerNode().execute(_ctx_for(node, [plain]), [plain])
    assert out[0][0].json == {"some": "payload"}


async def test_schedule_trigger_annotates_tick_with_fired_at() -> None:
    node = Node(id="node_1", name="Schedule", type="weftlyflow.schedule_trigger")
    out = await ScheduleTriggerNode().execute(_ctx_for(node, []), [])
    [tick] = out[0]
    assert "fired_at" in tick.json


async def test_schedule_trigger_preserves_seed_items() -> None:
    node = Node(id="node_1", name="Schedule", type="weftlyflow.schedule_trigger")
    seeded = [Item(json={"x": 1}), Item(json={"x": 2})]
    out = await ScheduleTriggerNode().execute(_ctx_for(node, seeded), seeded)
    [tick] = out[0]
    assert tick.json["seed"] == [{"x": 1}, {"x": 2}]
