"""Execution DTO ↔ domain mapper."""

from __future__ import annotations

from typing import TYPE_CHECKING

from weftlyflow.server.schemas.executions import ExecutionResponse, NodeRunDataDTO

if TYPE_CHECKING:
    from weftlyflow.domain.execution import Execution, NodeRunData


def execution_to_response(execution: Execution) -> ExecutionResponse:
    """Project a domain :class:`Execution` onto the wire format."""
    return ExecutionResponse(
        id=execution.id,
        workflow_id=execution.workflow_id,
        mode=execution.mode,
        status=execution.status,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        triggered_by=execution.triggered_by,
        run_data={
            node_id: [_node_run_data_to_dto(r) for r in runs]
            for node_id, runs in execution.run_data.per_node.items()
        },
    )


def _node_run_data_to_dto(nrd: NodeRunData) -> NodeRunDataDTO:
    return NodeRunDataDTO(
        items=[[dict(item.json) for item in port] for port in nrd.items],
        execution_time_ms=nrd.execution_time_ms,
        started_at=nrd.started_at,
        status=nrd.status,
        error=(
            {
                "message": nrd.error.message,
                "description": nrd.error.description,
                "code": nrd.error.code,
            }
            if nrd.error is not None
            else None
        ),
    )
