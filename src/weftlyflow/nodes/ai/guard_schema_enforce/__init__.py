"""Guardrail: validate item JSON against a user-supplied schema.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.guard_schema_enforce.node import GuardSchemaEnforceNode

NODE = GuardSchemaEnforceNode

__all__ = ["NODE", "GuardSchemaEnforceNode"]
