"""Function Call node — run another workflow as a sub-execution."""

from __future__ import annotations

from weftlyflow.nodes.core.function_call.node import FunctionCallNode

NODE = FunctionCallNode

__all__ = ["NODE", "FunctionCallNode"]
