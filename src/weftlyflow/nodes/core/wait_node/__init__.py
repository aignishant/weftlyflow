"""Wait node — pause execution by duration or until an absolute time."""

from __future__ import annotations

from weftlyflow.nodes.core.wait_node.node import WaitNode

NODE = WaitNode

__all__ = ["NODE", "WaitNode"]
