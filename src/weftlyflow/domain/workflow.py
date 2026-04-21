"""Workflow domain objects — the structural definition of a Weftlyflow workflow.

A :class:`Workflow` is a directed graph of :class:`Node` objects wired by
:class:`Connection` objects. Both nodes and connections are plain dataclasses
— the executor (in :mod:`weftlyflow.engine`) consumes this shape and never
mutates it in place.

Construction happens from either:
    - the REST API (Pydantic DTO → dataclass via a mapper), or
    - an Alembic-backed row (SQLAlchemy entity → dataclass via a mapper).

Neither path is visible from this module; keeping IO out is load-bearing.

See IMPLEMENTATION_BIBLE.md §7.1 for the full shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PortKind = Literal["main", "ai_tool", "ai_memory", "ai_embedding", "ai_document", "ai_model"]


@dataclass(slots=True, frozen=True)
class Port:
    """A typed input or output port on a node.

    Attributes:
        name: Logical name (``"main"``, ``"true"``, ``"false"``, ``"ai_tool"``).
        kind: Data category — determines which other nodes can connect to it.
        index: Zero-based index when a node has multiple ports of the same name.
        display_name: Optional UI label; falls back to ``name`` when missing.
        required: If True and no connection attaches here, the workflow is invalid.
    """

    name: str
    kind: PortKind = "main"
    index: int = 0
    display_name: str | None = None
    required: bool = False


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    """Per-node retry configuration.

    Attributes:
        max_attempts: Total attempts including the first. ``1`` means no retry.
        backoff_factor: Multiplier applied to ``base_delay_ms`` between attempts.
        base_delay_ms: Delay before the first retry.
        max_delay_ms: Upper bound on any retry delay.
    """

    max_attempts: int = 1
    backoff_factor: float = 2.0
    base_delay_ms: int = 1_000
    max_delay_ms: int = 60_000


@dataclass(slots=True)
class Node:
    """One step in a workflow.

    Attributes:
        id: Stable identifier (``node_<ulid>``). Persistent across edits.
        name: User-visible label shown in the editor.
        type: Registry key (``"weftlyflow.http_request"``). Keyed by ``(type, type_version)``.
        type_version: Which version of the node implementation to run.
        parameters: Validated against the node's ``PropertySchema`` list.
        credentials: Map from credential-slot-name (declared on the node spec) to credential id.
        position: ``(x, y)`` canvas coordinates — UI only, never used by the engine.
        disabled: If True, the engine skips the node (no run-data emitted).
        notes: Free-form markdown comment.
        continue_on_fail: If True, an exception becomes an error item rather than stopping the run.
        retry_policy: Optional per-node retry; absent means "fail fast".
    """

    id: str
    name: str
    type: str
    type_version: int = 1
    parameters: dict[str, Any] = field(default_factory=dict)
    credentials: dict[str, str] = field(default_factory=dict)
    position: tuple[float, float] = (0.0, 0.0)
    disabled: bool = False
    notes: str | None = None
    continue_on_fail: bool = False
    retry_policy: RetryPolicy | None = None


@dataclass(slots=True, frozen=True)
class Connection:
    """A directed edge from one node's output port to another node's input port.

    Attributes:
        source_node: ID of the upstream node.
        source_port: Port name on the source side (``"main"`` by default).
        source_index: Zero-based index when the port has multiple sockets.
        target_node: ID of the downstream node.
        target_port: Port name on the target side.
        target_index: Zero-based index on the target side.
    """

    source_node: str
    target_node: str
    source_port: str = "main"
    source_index: int = 0
    target_port: str = "main"
    target_index: int = 0


@dataclass(slots=True)
class WorkflowSettings:
    """Execution-time flags for a workflow.

    Attributes:
        timezone: IANA name. Affects cron triggers and ``$now`` / ``$today``.
        timeout_seconds: Hard wall-clock timeout for a full execution.
        save_manual_executions: Persist manual runs in the executions table.
        save_trigger_executions_on: ``"all"``, ``"error"``, or ``"none"``.
        error_workflow_id: Optional ID of a workflow that runs on failure.
        caller_policy: ``"any"`` / ``"own"`` / ``"none"`` — who can call this via Execute-Workflow.
    """

    timezone: str = "UTC"
    timeout_seconds: int = 3600
    save_manual_executions: bool = True
    save_trigger_executions_on: Literal["all", "error", "none"] = "all"
    error_workflow_id: str | None = None
    caller_policy: Literal["any", "own", "none"] = "own"


@dataclass(slots=True)
class Workflow:
    """A full workflow definition.

    Equality is by ``id``; two workflow instances with the same ID refer to the
    same logical workflow even if their in-memory representation differs.

    Attributes:
        id: Identifier.
        project_id: The owning project (multi-tenancy boundary).
        name: Display name.
        nodes: Nodes keyed by ``Node.id`` inside the list (never as a dict).
        connections: Directed edges. Duplicate edges are a validation error
            caught in ``engine.graph``; this dataclass does not enforce uniqueness.
        settings: Execution flags.
        static_data: Persistent per-workflow KV — readable/writable by nodes across runs.
        pin_data: ``{node_id: list[item_json]}`` — test-mode pinned outputs.
        active: True when triggers/webhooks are live.
        archived: Soft-deleted.
        tags: Freeform labels for filtering.
        version_id: Opaque token that changes on every save — used for optimistic concurrency.
    """

    id: str
    project_id: str
    name: str
    nodes: list[Node] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    settings: WorkflowSettings = field(default_factory=WorkflowSettings)
    static_data: dict[str, Any] = field(default_factory=dict)
    pin_data: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    active: bool = False
    archived: bool = False
    tags: list[str] = field(default_factory=list)
    version_id: str | None = None

    def node_by_id(self, node_id: str) -> Node | None:
        """Return the node with the given ID, or None if absent."""
        return next((n for n in self.nodes if n.id == node_id), None)
