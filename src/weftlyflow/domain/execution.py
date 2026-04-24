"""Execution domain objects — a frozen snapshot of one workflow run.

An :class:`Execution` owns a :class:`RunData` tree: one list of
:class:`NodeRunData` per node, enabling loops (a node can run multiple times).
Each node run contains a nested list of :class:`Item` values — the outer axis
is output-port index, the inner axis is the iterated items.

See weftlyinfo.md §7.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from weftlyflow.domain.workflow import Workflow

ExecutionMode = Literal["manual", "trigger", "webhook", "retry", "test"]
ExecutionStatus = Literal["new", "running", "success", "error", "waiting", "canceled"]
DataStorage = Literal["db", "fs", "s3"]


@dataclass(slots=True, frozen=True)
class PairedItem:
    """Provenance link — which upstream item produced this item.

    Used by the UI to show lineage in the run inspector and by expressions
    that reach into ``$("Previous Node").item.pairedItem``.
    """

    item_index: int
    input_index: int = 0
    source_override: str | None = None  # optional node id


@dataclass(slots=True)
class BinaryRef:
    """Pointer to binary data that does not live inline in the item JSON.

    Attributes:
        filename: Original filename, if known.
        mime_type: MIME type (``"application/pdf"``).
        size_bytes: Length in bytes.
        data_ref: Opaque handle (``"db:<id>"``, ``"fs:/path"``, ``"s3://bucket/key"``).
    """

    filename: str | None
    mime_type: str
    size_bytes: int
    data_ref: str


@dataclass(slots=True)
class NodeError:
    """Structured error attached to an item when ``continue_on_fail`` is True.

    Attributes:
        message: Human-readable message.
        description: Optional longer detail (e.g. a traceback summary).
        code: Optional machine-readable code.
    """

    message: str
    description: str | None = None
    code: str | None = None


@dataclass(slots=True)
class Item:
    """One record flowing between nodes.

    ``json`` carries the structured payload; ``binary`` holds references to
    large blobs that bypass the JSON column; ``paired_item`` preserves lineage.

    Attributes:
        json: The structured payload.
        binary: Named binary attachments.
        paired_item: Provenance — which upstream item produced this item.
        error: Present only when the producing node failed with ``continue_on_fail``.
    """

    json: dict[str, Any] = field(default_factory=dict)
    binary: dict[str, BinaryRef] = field(default_factory=dict)
    paired_item: list[PairedItem] = field(default_factory=list)
    error: NodeError | None = None


@dataclass(slots=True)
class NodeRunData:
    """One recorded run of a single node within an execution.

    Attributes:
        items: ``[output_port_index][item_index]`` of output items.
        execution_time_ms: Wall-clock duration.
        started_at: UTC timestamp when the node started.
        status: ``"success"`` / ``"error"`` / ``"disabled"``.
        error: Node-level error when ``status == "error"`` and items is empty.
    """

    items: list[list[Item]]
    execution_time_ms: int
    started_at: datetime
    status: Literal["success", "error", "disabled"]
    error: NodeError | None = None


@dataclass(slots=True)
class RunData:
    """All node runs recorded during an execution.

    ``per_node[node_id]`` is a list (not a single entry) because loop constructs
    can re-run the same node multiple times.
    """

    per_node: dict[str, list[NodeRunData]] = field(default_factory=dict)


@dataclass(slots=True)
class Execution:
    """One run of a workflow, from start to terminal state.

    The ``workflow_snapshot`` is a deep copy taken when the execution begins —
    this keeps reruns deterministic even if the live workflow is edited
    mid-execution.

    Attributes:
        id: ``ex_<ulid>``.
        workflow_id: ID of the live workflow that spawned this execution.
        workflow_snapshot: Frozen copy at run start.
        mode: How the run was triggered.
        status: Current state.
        started_at: UTC timestamp when the run began.
        finished_at: UTC timestamp when the run reached a terminal state.
        wait_till: If status is ``"waiting"``, the resume deadline.
        run_data: Per-node captures.
        data_storage: Where ``run_data`` is persisted (db/fs/s3).
        triggered_by: User ID, webhook ID, or schedule ID (free-form).
    """

    id: str
    workflow_id: str
    workflow_snapshot: Workflow
    mode: ExecutionMode
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    wait_till: datetime | None = None
    run_data: RunData = field(default_factory=RunData)
    data_storage: DataStorage = "db"
    triggered_by: str | None = None
