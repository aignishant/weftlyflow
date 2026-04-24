"""Guardrail: redact personally identifiable information from text.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.guard_pii_redact.node import GuardPiiRedactNode

NODE = GuardPiiRedactNode

__all__ = ["NODE", "GuardPiiRedactNode"]
