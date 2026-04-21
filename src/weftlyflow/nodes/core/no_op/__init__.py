"""No-op node — pass-through used for placeholders and testing."""

from __future__ import annotations

from weftlyflow.nodes.core.no_op.node import NoOpNode

NODE = NoOpNode

__all__ = ["NODE", "NoOpNode"]
