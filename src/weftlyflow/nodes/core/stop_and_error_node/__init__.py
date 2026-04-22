"""Stop & Error node — abort the execution with a resolved error message."""

from __future__ import annotations

from weftlyflow.nodes.core.stop_and_error_node.node import StopAndErrorNode

NODE = StopAndErrorNode

__all__ = ["NODE", "StopAndErrorNode"]
