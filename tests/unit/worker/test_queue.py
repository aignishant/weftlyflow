"""Unit tests for the execution-queue abstractions."""

from __future__ import annotations

from typing import Any

import pytest

from weftlyflow.worker.queue import CeleryExecutionQueue, ExecutionRequest


def test_execution_request_round_trips_through_dict() -> None:
    request = ExecutionRequest(
        execution_id="ex_1",
        workflow_id="wf_1",
        project_id="pr_1",
        mode="webhook",
        triggered_by="webhook:wh_1",
        initial_items=[{"foo": "bar"}],
    )
    copy = ExecutionRequest.from_dict(request.to_dict())
    assert copy == request


def test_execution_request_missing_optional_fields_default() -> None:
    req = ExecutionRequest.from_dict(
        {
            "execution_id": "ex_2",
            "workflow_id": "wf_2",
            "project_id": "pr_2",
            "mode": "trigger",
        },
    )
    assert req.triggered_by is None
    assert req.initial_items == []


class _FakeTask:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def apply_async(self, *, kwargs: dict[str, Any], task_id: str) -> None:
        self.calls.append({"kwargs": kwargs, "task_id": task_id})


@pytest.mark.asyncio
async def test_celery_queue_forwards_payload_to_apply_async() -> None:
    task = _FakeTask()
    queue = CeleryExecutionQueue(task=task)
    request = ExecutionRequest(
        execution_id="ex_3",
        workflow_id="wf_3",
        project_id="pr_3",
        mode="webhook",
    )
    await queue.enqueue(request)
    assert task.calls == [
        {
            "kwargs": {"payload": request.to_dict()},
            "task_id": "ex_3",
        },
    ]
