"""Code node — run a sandboxed Python snippet per item or per run.

Snippets execute inside a subprocess sandbox (:mod:`weftlyflow.worker.sandbox_runner`)
with OS-level ``rlimit`` + ``no-new-privs`` applied. The subprocess
interprets the snippet through :mod:`RestrictedPython` in ``exec`` mode,
so the defence is layered: syntax-level rejection of dangerous constructs,
runtime ``_getattr_`` guard, and OS-level process confinement.

Empty snippets remain a benign identity pass-through so workflows that
were saved against earlier stub versions don't start executing anything
the first time the sandbox becomes available.

Registration is gated behind ``settings.enable_code_node`` (see
:mod:`weftlyflow.nodes.core.code.__init__`); operators must opt in
explicitly. See weftlyinfo.md §10 and §26 risk #2 for the
threat model.
"""

from __future__ import annotations

from typing import ClassVar

import structlog

from weftlyflow.domain.errors import NodeExecutionError
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
from weftlyflow.worker.sandbox_runner import (
    SandboxError,
    SandboxSnippetError,
    SandboxTimeoutError,
    build_limits_from_settings,
    run_snippet,
)

log = structlog.get_logger(__name__)


class CodeNode(BaseNode):
    """Execute a Python snippet against the incoming items.

    The snippet surface is currently unimplemented; a non-empty ``code``
    parameter raises :class:`NodeExecutionError`. Empty snippets remain a
    benign identity pass-through so serialisation tests stay green.
    """

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
        """Execute ``code`` against ``items`` inside the subprocess sandbox.

        Empty snippets pass items through unchanged — the harmless
        identity path. Non-empty snippets are forwarded to
        :func:`weftlyflow.worker.sandbox_runner.run_snippet`, which
        forks a child process with rlimits applied and interprets the
        snippet through :mod:`RestrictedPython`.

        Raises:
            NodeExecutionError: when the snippet times out, escapes the
                sandbox syntax guard, or returns a malformed result.
        """
        raw = ctx.param("code", default="")
        snippet = raw if isinstance(raw, str) else ""
        if not snippet.strip():
            return [list(items)]

        request_items = [dict(item.json) for item in items]
        try:
            response_items = run_snippet(
                snippet,
                request_items,
                limits=build_limits_from_settings(),
            )
        except SandboxTimeoutError as exc:
            raise NodeExecutionError(
                f"code node timed out: {exc}",
                node_id=ctx.node.id,
                original=exc,
            ) from exc
        except SandboxSnippetError as exc:
            raise NodeExecutionError(
                f"code node snippet failed: {exc}",
                node_id=ctx.node.id,
                original=exc,
            ) from exc
        except SandboxError as exc:
            raise NodeExecutionError(
                f"code node sandbox error: {exc}",
                node_id=ctx.node.id,
                original=exc,
            ) from exc
        return [[Item(json=row) for row in response_items]]
