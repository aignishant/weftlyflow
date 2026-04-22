"""Turn a parsed webhook request into a queued workflow execution.

The handler is deliberately small — route matching lives in the registry,
request parsing lives in :mod:`weftlyflow.webhooks.parser`, and execution
happens in :mod:`weftlyflow.worker.execution`. This module is the glue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from weftlyflow.domain.ids import new_execution_id

if TYPE_CHECKING:
    from weftlyflow.worker.queue import ExecutionQueue, ExecutionRequest


@dataclass(slots=True, frozen=True)
class EnqueueResult:
    """Outcome returned to the ingress route after a webhook match.

    Attributes:
        execution_id: The ``ex_<ulid>`` identifier reserved for the run.
        accepted: True on the happy path; False when the queue refused the
            request (should never happen in Phase 3 but kept for forward
            compat with rate limiting).
    """

    execution_id: str
    accepted: bool = True


async def enqueue_from_webhook(
    *,
    queue: ExecutionQueue,
    workflow_id: str,
    project_id: str,
    node_id: str,
    request_payload: dict[str, Any],
    triggered_by: str,
) -> EnqueueResult:
    """Reserve an execution id and hand a request off to ``queue``.

    The execution id is allocated here so the ingress route can return it in
    the response body before the worker picks up the job. Consumers can poll
    ``GET /api/v1/executions/{id}`` to observe the run's progress.
    """
    execution_id = new_execution_id()
    request: ExecutionRequest = _build_request(
        execution_id=execution_id,
        workflow_id=workflow_id,
        project_id=project_id,
        node_id=node_id,
        request_payload=request_payload,
        triggered_by=triggered_by,
    )
    await queue.enqueue(request)
    return EnqueueResult(execution_id=execution_id)


def _build_request(
    *,
    execution_id: str,
    workflow_id: str,
    project_id: str,
    node_id: str,
    request_payload: dict[str, Any],
    triggered_by: str,
) -> ExecutionRequest:
    # Import here to avoid a circular dependency at module import time: the
    # queue module imports the handler's EnqueueResult in its public docs.
    from weftlyflow.worker.queue import ExecutionRequest  # noqa: PLC0415

    return ExecutionRequest(
        execution_id=execution_id,
        workflow_id=workflow_id,
        project_id=project_id,
        mode="webhook",
        triggered_by=triggered_by,
        initial_items=[{"node_id": node_id, "request": request_payload}],
    )
