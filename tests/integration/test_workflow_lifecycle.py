"""Phase-2 acceptance — POST a workflow, execute it, read back the execution.

Walks the spec's acceptance sentence literally:
    "A user can POST a workflow, execute it via the API, and read back the
    execution."

Also exercises CRUD edges (404s, PUT, DELETE, list) so every route has at
least one happy-path + one sad-path assertion.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


def _five_node_body() -> dict:
    return {
        "name": "five-node-acceptance",
        "nodes": [
            {"id": "node_trigger", "name": "Trigger", "type": "weftlyflow.manual_trigger"},
            {
                "id": "node_set",
                "name": "Tagger",
                "type": "weftlyflow.set",
                "parameters": {"assignments": [{"name": "tagged", "value": True}]},
            },
            {
                "id": "node_if",
                "name": "Adult?",
                "type": "weftlyflow.if",
                "parameters": {
                    "field": "age",
                    "operator": "greater_than_or_equal",
                    "value": 18,
                },
            },
            {"id": "node_adults", "name": "Adults", "type": "weftlyflow.no_op"},
            {"id": "node_minors", "name": "Minors", "type": "weftlyflow.no_op"},
        ],
        "connections": [
            {"source_node": "node_trigger", "target_node": "node_set"},
            {"source_node": "node_set", "target_node": "node_if"},
            {
                "source_node": "node_if",
                "target_node": "node_adults",
                "source_port": "true",
                "source_index": 0,
            },
            {
                "source_node": "node_if",
                "target_node": "node_minors",
                "source_port": "false",
                "source_index": 1,
            },
        ],
    }


async def test_post_workflow_execute_read(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    # 1. POST the workflow.
    create = await client.post(
        "/api/v1/workflows", headers=auth_headers, json=_five_node_body(),
    )
    assert create.status_code == 201, create.text
    wf_id = create.json()["id"]
    assert wf_id.startswith("wf_")

    # 2. Execute it.
    execute = await client.post(
        f"/api/v1/workflows/{wf_id}/execute",
        headers=auth_headers,
        json={
            "initial_items": [
                {"age": 30},
                {"age": 10},
                {"age": 21},
            ],
        },
    )
    assert execute.status_code == 200, execute.text
    exec_body = execute.json()
    assert exec_body["status"] == "success"
    execution_id = exec_body["id"]

    # 3. Read it back via the executions router.
    read = await client.get(
        f"/api/v1/executions/{execution_id}", headers=auth_headers,
    )
    assert read.status_code == 200
    read_body = read.json()
    assert read_body["status"] == "success"
    assert read_body["workflow_id"] == wf_id

    # 4. Verify the run-data shape — adults vs. minors routing.
    run_data = read_body["run_data"]
    assert set(run_data) == {"node_trigger", "node_set", "node_if", "node_adults", "node_minors"}

    adults_port = run_data["node_adults"][0]["items"][0]
    minors_port = run_data["node_minors"][0]["items"][0]
    assert [item["json"]["age"] for item in adults_port] == [30, 21]
    assert [item["json"]["age"] for item in minors_port] == [10]
    assert all(item["json"]["tagged"] is True for item in adults_port + minors_port)


async def test_get_workflow_404(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    resp = await client.get("/api/v1/workflows/wf_missing", headers=auth_headers)
    assert resp.status_code == 404


async def test_list_workflows_empty_then_one(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    first = await client.get("/api/v1/workflows", headers=auth_headers)
    assert first.status_code == 200
    assert first.json() == []

    create = await client.post(
        "/api/v1/workflows",
        headers=auth_headers,
        json={"name": "solo"},
    )
    assert create.status_code == 201

    second = await client.get("/api/v1/workflows", headers=auth_headers)
    assert len(second.json()) == 1


async def test_update_workflow(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    create = await client.post(
        "/api/v1/workflows", headers=auth_headers, json={"name": "before"},
    )
    wf_id = create.json()["id"]

    put = await client.put(
        f"/api/v1/workflows/{wf_id}",
        headers=auth_headers,
        json={"name": "after", "active": True},
    )
    assert put.status_code == 200
    assert put.json()["name"] == "after"
    assert put.json()["active"] is True


async def test_delete_workflow(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    create = await client.post(
        "/api/v1/workflows", headers=auth_headers, json={"name": "doomed"},
    )
    wf_id = create.json()["id"]

    delete = await client.delete(f"/api/v1/workflows/{wf_id}", headers=auth_headers)
    assert delete.status_code == 204

    read = await client.get(f"/api/v1/workflows/{wf_id}", headers=auth_headers)
    assert read.status_code == 404


async def test_execute_unknown_workflow_is_404(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    resp = await client.post(
        "/api/v1/workflows/wf_missing/execute",
        headers=auth_headers,
        json={"initial_items": []},
    )
    assert resp.status_code == 404


async def test_execute_cycle_returns_400(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    create = await client.post(
        "/api/v1/workflows",
        headers=auth_headers,
        json={
            "name": "cycle",
            "nodes": [
                {"id": "a", "name": "A", "type": "weftlyflow.no_op"},
                {"id": "b", "name": "B", "type": "weftlyflow.no_op"},
            ],
            "connections": [
                {"source_node": "a", "target_node": "b"},
                {"source_node": "b", "target_node": "a"},
            ],
        },
    )
    wf_id = create.json()["id"]
    resp = await client.post(
        f"/api/v1/workflows/{wf_id}/execute", headers=auth_headers, json={},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "cycle_detected"


async def test_list_executions_shows_history(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    create = await client.post(
        "/api/v1/workflows", headers=auth_headers, json=_five_node_body(),
    )
    wf_id = create.json()["id"]

    for _ in range(3):
        resp = await client.post(
            f"/api/v1/workflows/{wf_id}/execute",
            headers=auth_headers,
            json={"initial_items": [{"age": 25}]},
        )
        assert resp.status_code == 200

    listing = await client.get(
        "/api/v1/executions",
        headers=auth_headers,
        params={"workflow_id": wf_id},
    )
    assert listing.status_code == 200
    assert len(listing.json()) == 3
