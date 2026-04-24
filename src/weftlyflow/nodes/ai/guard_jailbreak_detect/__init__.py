"""Guardrail: detect common prompt-injection / jailbreak patterns.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.guard_jailbreak_detect.node import GuardJailbreakDetectNode

NODE = GuardJailbreakDetectNode

__all__ = ["NODE", "GuardJailbreakDetectNode"]
