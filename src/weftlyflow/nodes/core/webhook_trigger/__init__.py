"""Webhook-trigger node — start a workflow from an inbound HTTP request."""

from __future__ import annotations

from weftlyflow.nodes.core.webhook_trigger.node import WebhookTriggerNode

NODE = WebhookTriggerNode

__all__ = ["NODE", "WebhookTriggerNode"]
