"""Agent ReAct node - composed single-turn ReAct orchestrator.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.agent_react.node import AgentReactNode

NODE = AgentReactNode

__all__ = ["NODE", "AgentReactNode"]
