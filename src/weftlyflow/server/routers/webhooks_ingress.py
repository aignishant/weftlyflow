"""Public webhook ingress — ``ANY /webhook/{path:path}``.

This router sits **outside** ``/api/v1/`` because the endpoints are hit by
arbitrary third parties. No bearer auth, no project header — the webhook id
embedded in the URL path is the only authentication, so the registered
paths should be unguessable (or behind a reverse-proxy ACL).

Request flow:

1. Match ``(path, method)`` against the in-memory registry.
2. On miss, 404.
3. On hit, parse the request into :class:`ParsedRequest` + enqueue via the
   configured :class:`ExecutionQueue`.
4. Return 202 immediately with the reserved execution id so callers can
   poll ``GET /api/v1/executions/{id}``.

``response_mode=when_finished`` will be supported in Phase 4 once
`weftlyflow.engine` exposes a completion future.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from weftlyflow.webhooks.constants import WEBHOOK_URL_PREFIX
from weftlyflow.webhooks.handler import enqueue_from_webhook
from weftlyflow.webhooks.parser import parse_request

if TYPE_CHECKING:
    from weftlyflow.webhooks.registry import WebhookRegistry
    from weftlyflow.worker.queue import ExecutionQueue

router = APIRouter(prefix=WEBHOOK_URL_PREFIX, tags=["webhooks"])


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    summary="Webhook ingress — matches any registered webhook path",
)
async def ingest_webhook(path: str, request: Request) -> JSONResponse:
    """Dispatch an incoming request to the matching workflow.

    Returns 404 when no webhook is registered at ``(path, method)``. On a
    successful enqueue the response is 202 with the reserved execution id.
    """
    registry: WebhookRegistry = request.app.state.webhook_registry
    queue: ExecutionQueue = request.app.state.execution_queue

    entry = registry.match(path, request.method)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no webhook registered for {request.method} /webhook/{path}",
        )

    body = await request.body()
    parsed = parse_request(
        method=request.method,
        path=path,
        headers=list(request.headers.items()),
        query_items=list(request.query_params.multi_items()),
        body=body,
    )

    payload: dict[str, Any] = {
        "method": parsed.method,
        "path": parsed.path,
        "headers": parsed.headers,
        "query": parsed.query,
        "query_all": parsed.query_all,
        "body": parsed.body,
    }

    result = await enqueue_from_webhook(
        queue=queue,
        workflow_id=entry.workflow_id,
        project_id=entry.project_id,
        node_id=entry.node_id,
        request_payload=payload,
        triggered_by=f"webhook:{entry.id}",
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"execution_id": result.execution_id, "accepted": result.accepted},
    )
