"""Domain-level exception hierarchy.

Every Weftlyflow exception inherits from :class:`WeftlyflowError`. Callers should
catch specific subclasses — the only place a bare ``WeftlyflowError`` catch is
acceptable is an outermost adapter (FastAPI exception handler, Celery task
boundary, CLI entry point).
"""

from __future__ import annotations


class WeftlyflowError(Exception):
    """Root of the Weftlyflow exception tree."""


class WorkflowValidationError(WeftlyflowError):
    """A workflow failed structural validation (duplicate node IDs, orphan connection)."""


class InvalidConnectionError(WorkflowValidationError):
    """A connection references a node or port that does not exist."""


class CycleDetectedError(WorkflowValidationError):
    """The workflow graph contains a non-whitelisted cycle."""


class NodeExecutionError(WeftlyflowError):
    """A node raised during execution.

    Attributes:
        node_id: The offending node.
        original: The underlying exception (preserved via ``__cause__``).
    """

    def __init__(
        self,
        message: str,
        *,
        node_id: str,
        original: BaseException | None = None,
    ) -> None:
        """Initialize with the offending ``node_id`` and optional underlying cause."""
        super().__init__(message)
        self.node_id = node_id
        self.original = original


class ExecutionCanceledError(WeftlyflowError):
    """The execution was canceled cooperatively (user-initiated or worker shutdown)."""


class ExpressionSyntaxError(WeftlyflowError):
    """A ``{{ ... }}`` block failed to compile."""


class ExpressionEvalError(WeftlyflowError):
    """A ``{{ ... }}`` block raised during evaluation."""


class ExpressionTimeoutError(WeftlyflowError):
    """A ``{{ ... }}`` block exceeded the soft timeout."""


class CredentialNotFoundError(WeftlyflowError):
    """A node asked for a credential slot that isn't configured."""


class CredentialDecryptError(WeftlyflowError):
    """A credential blob failed to decrypt — key rotation or corruption."""
