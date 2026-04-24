"""Agent Tool Dispatch node - fan LLM tool calls to a dedicated port.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.ai.agent_tool_dispatch.node import AgentToolDispatchNode

NODE = AgentToolDispatchNode

__all__ = ["NODE", "AgentToolDispatchNode"]
