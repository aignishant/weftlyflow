"""Code node — gated behind ``settings.enable_code_node``.

Registration is opt-in because the in-process RestrictedPython layer alone
is not a hardened-enough boundary for arbitrary user code. The node class
is always importable so tests and explicit registrations still work; only
the discovery hook (``NODE``) is suppressed when the flag is off.

Set ``WEFTLYFLOW_ENABLE_CODE_NODE=true`` once the subprocess sandbox
runner has landed and the operator understands the risk.
"""

from __future__ import annotations

from weftlyflow.config import get_settings
from weftlyflow.nodes.core.code.node import CodeNode

NODE: type[CodeNode] | None = CodeNode if get_settings().enable_code_node else None

__all__ = ["NODE", "CodeNode"]
