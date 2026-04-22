"""Phase-6 integration — chain the new Tier-1 nodes in a real workflow.

Covers two workflows via the HTTP API:

1. Filter → Rename Keys → Evaluate Expression → Switch — ensures each node
   sees the output of its upstream one and the executor routes Switch
   outputs correctly per the default/case ports.
2. Stop & Error — confirms the node surfaces a resolved error message in
   the persisted execution's status + run-data.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_chain_filter_rename_evaluate_switch(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    body = {
        "name": "phase6-chain",
        "nodes": [
            {
                "id": "node_trigger",
                "name": "Trigger",
                "type": "weftlyflow.manual_trigger",
            },
            {
                "id": "node_filter",
                "name": "Adults",
                "type": "weftlyflow.filter",
                "parameters": {
                    "field": "age",
                    "operator": "greater_than_or_equal",
                    "value": 18,
                },
            },
            {
                "id": "node_rename",
                "name": "Rename",
                "type": "weftlyflow.rename_keys",
                "parameters": {
                    "mappings": [{"from": "firstName", "to": "first_name"}],
                    "drop_missing": True,
                },
            },
            {
                "id": "node_eval",
                "name": "Tag",
                "type": "weftlyflow.evaluate_expression",
                "parameters": {
                    "expression": "{{ $json.first_name.upper() }}",
                    "output_field": "display_name",
                },
            },
            {
                "id": "node_switch",
                "name": "Route",
                "type": "weftlyflow.switch",
                "parameters": {
                    "field": "country",
                    "cases": [
                        {"value": "US", "port": "case_1"},
                        {"value": "GB", "port": "case_2"},
                    ],
                    "fallback_port": "default",
                },
            },
            {"id": "node_us", "name": "US", "type": "weftlyflow.no_op"},
            {"id": "node_gb", "name": "GB", "type": "weftlyflow.no_op"},
            {"id": "node_other", "name": "Other", "type": "weftlyflow.no_op"},
        ],
        "connections": [
            {"source_node": "node_trigger", "target_node": "node_filter"},
            {"source_node": "node_filter", "target_node": "node_rename"},
            {"source_node": "node_rename", "target_node": "node_eval"},
            {"source_node": "node_eval", "target_node": "node_switch"},
            {
                "source_node": "node_switch",
                "target_node": "node_us",
                "source_port": "case_1",
                "source_index": 0,
            },
            {
                "source_node": "node_switch",
                "target_node": "node_gb",
                "source_port": "case_2",
                "source_index": 1,
            },
            {
                "source_node": "node_switch",
                "target_node": "node_other",
                "source_port": "default",
                "source_index": 6,
            },
        ],
    }
    create = await client.post("/api/v1/workflows", headers=auth_headers, json=body)
    assert create.status_code == 201, create.text
    wf_id = create.json()["id"]

    execute = await client.post(
        f"/api/v1/workflows/{wf_id}/execute",
        headers=auth_headers,
        json={
            "initial_items": [
                {"age": 10, "firstName": "Ada", "country": "GB"},
                {"age": 30, "firstName": "Grace", "country": "US"},
                {"age": 21, "firstName": "Linus", "country": "FI"},
                {"age": 42, "firstName": "Edsger", "country": "NL"},
            ],
        },
    )
    assert execute.status_code == 200, execute.text
    payload = execute.json()
    assert payload["status"] == "success"

    run_data = payload["run_data"]

    # Filter drops the minor.
    filter_out = run_data["node_filter"][0]["items"][0]
    assert {it["age"] for it in filter_out} == {30, 21, 42}

    # Rename makes every kept item expose `first_name` not `firstName`.
    rename_out = run_data["node_rename"][0]["items"][0]
    assert all("first_name" in it and "firstName" not in it for it in rename_out)

    # Evaluate writes display_name via the expression engine.
    eval_out = run_data["node_eval"][0]["items"][0]
    assert {it["display_name"] for it in eval_out} == {"GRACE", "LINUS", "EDSGER"}

    # Switch routes by country.
    us_out = run_data["node_us"][0]["items"][0]
    gb_out = run_data["node_gb"][0]["items"][0]
    other_out = run_data["node_other"][0]["items"][0]
    assert [it["first_name"] for it in us_out] == ["Grace"]
    assert gb_out == []  # Ada was filtered before Switch
    assert {it["first_name"] for it in other_out} == {"Linus", "Edsger"}


async def test_stop_and_error_records_failed_execution(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    body = {
        "name": "phase6-stop",
        "nodes": [
            {"id": "node_trigger", "name": "Trigger", "type": "weftlyflow.manual_trigger"},
            {
                "id": "node_stop",
                "name": "Stop",
                "type": "weftlyflow.stop_and_error",
                "parameters": {
                    "message": "halt on id={{ $json.id }}",
                    "code": "manual_halt",
                },
            },
        ],
        "connections": [
            {"source_node": "node_trigger", "target_node": "node_stop"},
        ],
    }
    create = await client.post("/api/v1/workflows", headers=auth_headers, json=body)
    wf_id = create.json()["id"]

    execute = await client.post(
        f"/api/v1/workflows/{wf_id}/execute",
        headers=auth_headers,
        json={"initial_items": [{"id": 7}]},
    )
    assert execute.status_code == 200, execute.text
    body = execute.json()
    assert body["status"] == "error"
    stop_run = body["run_data"]["node_stop"][0]
    assert stop_run["status"] == "error"
    assert "halt on id=7" in (stop_run["error"]["message"] if stop_run.get("error") else "")
