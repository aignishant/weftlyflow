"""Code node — run a sandboxed Python snippet per item or per run.

Phase-1 implementation is an **identity pass-through**: the ``code`` parameter
is accepted and type-checked but not executed. The executor's
``continue_on_fail`` / retry / hook semantics can still be exercised through
this node while the sandbox is under construction.

Phase 4 replaces :meth:`CodeNode._run_snippet` with a ``RestrictedPython``
invocation that compiles the snippet once per run and evaluates it against a
hardened globals dict. The node spec and the public surface remain the same;
existing workflows continue to load.

See IMPLEMENTATION_BIBLE.md §10 and §14 for the sandbox design.
"""

from __future__ import annotations

from typing import ClassVar

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode


class CodeNode(BaseNode):
    """Execute a Python snippet against the incoming items (stubbed in Phase 1)."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.code",
        version=1,
        display_name="Code",
        description="Run a sandboxed Python snippet. Phase-1 build is an identity stub.",
        icon="icons/code.svg",
        category=NodeCategory.CORE,
        group=["transform", "advanced"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="mode",
                display_name="Mode",
                type="options",
                default="run_once_for_all",
                options=[
                    PropertyOption(value="run_once_for_all", label="Run once for all items"),
                    PropertyOption(value="run_once_per_item", label="Run once per item"),
                ],
            ),
            PropertySchema(
                name="code",
                display_name="Code",
                type="string",
                default="",
                type_options={"rows": 10, "language": "python"},
                description="Python snippet — ignored in Phase 1; sandbox lands in Phase 4.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Return the items unchanged. Real sandbox evaluation arrives in Phase 4."""
        snippet = ctx.param("code", default="")
        return [self._run_snippet(snippet=snippet if isinstance(snippet, str) else "", items=items)]

    def _run_snippet(self, *, snippet: str, items: list[Item]) -> list[Item]:
        """Identity in Phase 1. Kept as a seam so Phase 4 swaps the sandbox in here."""
        del snippet
        return list(items)
