"""Engine-layer exceptions.

These specialize :class:`weftlyflow.domain.errors.WeftlyflowError` for conditions
the executor can raise that are not meaningful at the domain layer (the domain
layer must not know about scheduling, readiness, or node lookup).
"""

from __future__ import annotations

from weftlyflow.domain.errors import WeftlyflowError


class EngineError(WeftlyflowError):
    """Base class for execution-engine failures."""


class NodeTypeNotFoundError(EngineError):
    """A workflow references a ``(type, version)`` that is not registered."""


class UnreachableNodeError(EngineError):
    """The executor computed a node as unreachable from the start node.

    This is a warning-level condition that the executor surfaces when strict
    mode is enabled; it is raised (rather than logged) only when the workflow
    was validated as having no disconnected subgraphs.
    """


class OutputPortIndexError(EngineError):
    """A node returned fewer output lists than its spec declares ports for."""
