"""PostHog integration — capture, batch ingestion, feature-flag decide.

Uses :class:`~weftlyflow.credentials.types.posthog_api.PostHogApiCredential`.
The project_api_key is carried inside the request body on every
ingestion call — the node folds it in immediately before dispatch.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.posthog.node import PostHogNode

NODE = PostHogNode

__all__ = ["NODE", "PostHogNode"]
