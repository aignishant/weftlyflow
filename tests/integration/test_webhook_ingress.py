"""Phase-3 acceptance — a webhook POST triggers a workflow and writes an execution.

Walks the bible's acceptance sentence literally:
    "An HTTP POST to a webhook URL triggers a workflow, which executes in a
    worker and writes the execution."

We use the in-process :class:`InlineExecutionQueue` as the worker substitute
so the tests don't need a live Redis + Celery — the production swap happens
at app-boot, not in the code paths being exercised here.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


def _two_node_webhook_body(*, path: str = "demo/hook") -> dict[str, Any]:
    return {
        "name": "webhook-demo",
        "nodes": [
            {
                "id": "node_trigger",
                "name": "Trigger",
                "type": "weftlyflow.webhook_trigger",
                "parameters": {"path": path, "method": "POST"},
            },
            {
                "id": "node_tag",
                "name": "Tag",
                "type": "weftlyflow.set",
                "parameters": {
                    "assignments": [{"name": "tagged", "value": True}],
                },
            },
        ],
        "connections": [
            {"source_node": "node_trigger", "target_node": "node_tag"},
        ],
    }


async def _wait_for_execution(
    client: AsyncClient,
    execution_id: str,
    *,
    auth_headers: dict[str, str],
    timeout: float = 3.0,
) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + timeout
    last: dict[str, Any] = {}
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(
            f"/api/v1/executions/{execution_id}", headers=auth_headers,
        )
        if resp.status_code == 200:
            last = resp.json()
            if last["status"] in {"success", "error"}:
                return last
        await asyncio.sleep(0.05)
    return last


async def test_webhook_activate_ingress_executes_workflow(
    client: AsyncClient,
    auth_headers: dict[str, str],
    execution_queue: Any,
) -> None:
    # 1. Create + activate the workflow.
    create = await client.post(
        "/api/v1/workflows", headers=auth_headers, json=_two_node_webhook_body(),
    )
    assert create.status_code == 201, create.text
    wf_id = create.json()["id"]

    activate = await client.post(
        f"/api/v1/workflows/{wf_id}/activate", headers=auth_headers,
    )
    assert activate.status_code == 200, activate.text
    assert activate.json()["active"] is True

    # 2. Hit the public webhook endpoint.
    hit = await client.post(
        "/webhook/demo/hook",
        json={"name": "world"},
    )
    assert hit.status_code == 202, hit.text
    execution_id = hit.json()["execution_id"]
    assert execution_id.startswith("ex_")

    # 3. The worker (InlineExecutionQueue) runs in the background; drain + poll.
    await execution_queue.drain()
    run = await _wait_for_execution(client, execution_id, auth_headers=auth_headers)
    assert run.get("status") == "success", run
    assert run["workflow_id"] == wf_id
    assert run["mode"] == "webhook"

    # 4. The Set node should see the flattened webhook body.
    tag_outputs = run["run_data"]["node_tag"][0]["items"][0]
    assert tag_outputs[0]["tagged"] is True
    assert tag_outputs[0]["body"] == {"name": "world"}


async def test_unregistered_webhook_returns_404(client: AsyncClient) -> None:
    resp = await client.post("/webhook/not-registered", json={})
    assert resp.status_code == 404


async def test_deactivate_removes_webhook_route(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    create = await client.post(
        "/api/v1/workflows",
        headers=auth_headers,
        json=_two_node_webhook_body(path="deactivate/me"),
    )
    wf_id = create.json()["id"]

    await client.post(f"/api/v1/workflows/{wf_id}/activate", headers=auth_headers)
    assert (await client.post("/webhook/deactivate/me", json={})).status_code == 202

    deactivate = await client.post(
        f"/api/v1/workflows/{wf_id}/deactivate", headers=auth_headers,
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["active"] is False

    missed = await client.post("/webhook/deactivate/me", json={})
    assert missed.status_code == 404


async def test_activate_reregisters_same_path_for_same_workflow(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    # Re-activating the same workflow must not raise a conflict — the
    # manager should tear down the prior registration first.
    create = await client.post(
        "/api/v1/workflows",
        headers=auth_headers,
        json=_two_node_webhook_body(path="reactivate/me"),
    )
    wf_id = create.json()["id"]

    first = await client.post(f"/api/v1/workflows/{wf_id}/activate", headers=auth_headers)
    second = await client.post(f"/api/v1/workflows/{wf_id}/activate", headers=auth_headers)
    assert first.status_code == 200
    assert second.status_code == 200
