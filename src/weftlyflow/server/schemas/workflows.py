"""Workflow DTOs — wire-format for create, read, update, and execute.

Intentionally a minimal projection of the domain dataclasses: exposing the
raw JSON-friendly shape lets the frontend round-trip a workflow unchanged.
Phase 2 does not add extra validation beyond Pydantic's structural checks;
the spec's §8 validation (cycles, orphan connections) runs inside
:class:`WorkflowGraph` before every execute.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from weftlyflow.server.schemas.common import WeftlyflowModel


class PortDTO(WeftlyflowModel):
    """One input/output port on a node."""

    name: str
    kind: str = "main"
    index: int = 0
    display_name: str | None = None
    required: bool = False


class RetryPolicyDTO(WeftlyflowModel):
    """Per-node retry configuration DTO."""

    max_attempts: int = 1
    backoff_factor: float = 2.0
    base_delay_ms: int = 1000
    max_delay_ms: int = 60000


class NodeDTO(WeftlyflowModel):
    """Wire-format for a :class:`~weftlyflow.domain.workflow.Node`."""

    id: str
    name: str
    type: str
    type_version: int = 1
    parameters: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, str] = Field(default_factory=dict)
    position: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    disabled: bool = False
    notes: str | None = None
    continue_on_fail: bool = False
    retry_policy: RetryPolicyDTO | None = None


class ConnectionDTO(WeftlyflowModel):
    """Wire-format for a :class:`~weftlyflow.domain.workflow.Connection`."""

    source_node: str
    target_node: str
    source_port: str = "main"
    source_index: int = 0
    target_port: str = "main"
    target_index: int = 0


class WorkflowSettingsDTO(WeftlyflowModel):
    """Wire-format for :class:`~weftlyflow.domain.workflow.WorkflowSettings`."""

    timezone: str = "UTC"
    timeout_seconds: int = 3600
    save_manual_executions: bool = True
    save_trigger_executions_on: str = "all"
    error_workflow_id: str | None = None
    caller_policy: str = "own"


class WorkflowCreateRequest(WeftlyflowModel):
    """Body for ``POST /api/v1/workflows``."""

    name: str = Field(min_length=1, max_length=200)
    nodes: list[NodeDTO] = Field(default_factory=list)
    connections: list[ConnectionDTO] = Field(default_factory=list)
    settings: WorkflowSettingsDTO = Field(default_factory=WorkflowSettingsDTO)
    tags: list[str] = Field(default_factory=list)


class WorkflowUpdateRequest(WorkflowCreateRequest):
    """Body for ``PUT /api/v1/workflows/{id}`` — same shape as create."""

    active: bool = False
    archived: bool = False


class WorkflowResponse(WeftlyflowModel):
    """Response body for GET/POST/PUT on workflows."""

    id: str
    project_id: str
    name: str
    nodes: list[NodeDTO]
    connections: list[ConnectionDTO]
    settings: WorkflowSettingsDTO
    tags: list[str]
    active: bool
    archived: bool


class WorkflowExecuteRequest(WeftlyflowModel):
    """Body for ``POST /api/v1/workflows/{id}/execute``."""

    initial_items: list[dict[str, Any]] = Field(default_factory=list)
