"""Agent Tool Result node - encode tool outputs back into LLM message shape.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.agent_tool_result.node import AgentToolResultNode

NODE = AgentToolResultNode

__all__ = ["NODE", "AgentToolResultNode"]
