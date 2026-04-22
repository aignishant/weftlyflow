"""Webhook-trigger node — emits the inbound request as the workflow's seed item.

The node is modelled as an action node even though conceptually it is a
trigger: at execution time, the webhook handler has already seeded the
workflow with a single item containing the parsed request. The node's job is
to unwrap that item into a more ergonomic shape (``{"body": ..., "query": ...,
"headers": ..., "method": ..., "path": ...}``) so downstream expressions can
read ``$json.body.foo`` without having to traverse the trigger-internal
wrapper.

Trigger-subsystem registration (adding a row to the ``webhooks`` table,
installing an external subscription) is handled by
:class:`weftlyflow.triggers.manager.ActiveTriggerManager` based on the
node's ``type`` string — it does not go through the node instance.
"""

from __future__ import annotations

from typing import ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode
from weftlyflow.webhooks.constants import (
    RESPONSE_IMMEDIATELY,
    RESPONSE_MODES,
    SUPPORTED_METHODS,
)

_REQUEST_KEY = "request"


class WebhookTriggerNode(BaseNode):
    """Start a workflow from an inbound HTTP request; forward the request as an item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.webhook_trigger",
        version=1,
        display_name="Webhook Trigger",
        description="Start the workflow when an HTTP request arrives at the registered path.",
        icon="icons/webhook-trigger.svg",
        category=NodeCategory.TRIGGER,
        group=["trigger"],
        inputs=[],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="path",
                display_name="Path",
                type="string",
                default="",
                description=(
                    "Path suffix this trigger listens on. "
                    "Leave empty to use the workflow/node id."
                ),
            ),
            PropertySchema(
                name="method",
                display_name="HTTP Method",
                type="options",
                default="POST",
                required=True,
                options=[PropertyOption(value=m, label=m) for m in SUPPORTED_METHODS],
            ),
            PropertySchema(
                name="response_mode",
                display_name="Response mode",
                type="options",
                default=RESPONSE_IMMEDIATELY,
                options=[PropertyOption(value=m, label=m) for m in RESPONSE_MODES],
                description="Return 202 immediately, or wait for the workflow to finish.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Unwrap the seeded request item(s) into an ergonomic shape."""
        del ctx
        outputs: list[Item] = []
        for item in items:
            outputs.append(_flatten_request_item(item))
        return [outputs]


def _flatten_request_item(item: Item) -> Item:
    request = item.json.get(_REQUEST_KEY) if isinstance(item.json, dict) else None
    if not isinstance(request, dict):
        return item
    flattened = {
        "method": request.get("method"),
        "path": request.get("path"),
        "headers": request.get("headers", {}),
        "query": request.get("query", {}),
        "query_all": request.get("query_all", {}),
        "body": request.get("body"),
    }
    return Item(json=flattened, binary=item.binary, paired_item=item.paired_item, error=item.error)
