"""Polling loop primitives.

Phase 3 does not yet ship a poller-driven integration (Slack, Gmail, etc.)
— those land in Phase 6. The module still exists so

* the trigger manager can depend on ``BasePollerNode`` integration here,
* the scheduler has a home to invoke polling callbacks from,
* we can unit-test the callback contract in isolation.

A polling run is little more than: "call ``BasePollerNode.poll()``; if it
returns items, enqueue an execution seeded with those items". That fits in
one function.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from weftlyflow.domain.execution import Item
    from weftlyflow.nodes.base import BasePollerNode
    from weftlyflow.worker.queue import ExecutionQueue, ExecutionRequest

log = structlog.get_logger(__name__)


async def run_poll_tick(
    *,
    node: BasePollerNode,
    ctx: Any,
    queue: ExecutionQueue,
    build_request: Any,
) -> int:
    """Invoke ``node.poll(ctx)``; enqueue an execution if it yielded items.

    Args:
        node: The concrete :class:`BasePollerNode` instance.
        ctx: The :class:`PollContext` forwarded to ``poll()``.
        queue: Where to send the resulting :class:`ExecutionRequest`.
        build_request: Callable that takes the returned items list and
            returns an :class:`ExecutionRequest`.

    Returns:
        The number of items harvested (0 when the node returned ``None`` or
        an empty list).
    """
    items: list[Item] | None = await node.poll(ctx)
    if not items:
        return 0
    request: ExecutionRequest = build_request(items)
    await queue.enqueue(request)
    log.info("poll_tick_enqueued", count=len(items), execution_id=request.execution_id)
    return len(items)
