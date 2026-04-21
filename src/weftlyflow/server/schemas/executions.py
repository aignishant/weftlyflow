"""Execution DTOs — metadata list, detail, and run-data shape."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from weftlyflow.server.schemas.common import WeftlyflowModel


class ExecutionSummary(WeftlyflowModel):
    """Metadata row used by the list endpoint — excludes ``run_data``."""

    id: str
    workflow_id: str
    mode: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    triggered_by: str | None = None


class NodeRunDataDTO(WeftlyflowModel):
    """One node's run result inside an execution's ``run_data``."""

    items: list[list[dict[str, Any]]]
    execution_time_ms: int
    started_at: datetime
    status: str
    error: dict[str, Any] | None = None


class ExecutionResponse(ExecutionSummary):
    """Detail shape returned by ``GET /api/v1/executions/{id}``."""

    run_data: dict[str, list[NodeRunDataDTO]] = Field(default_factory=dict)
