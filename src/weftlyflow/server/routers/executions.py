"""Execution read endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status

from weftlyflow.auth.constants import SCOPE_EXECUTION_READ
from weftlyflow.db.repositories.execution_repo import ExecutionRepository
from weftlyflow.server.deps import get_current_project, get_db, require_scope
from weftlyflow.server.mappers.execution import execution_to_response
from weftlyflow.server.schemas.executions import ExecutionResponse, ExecutionSummary

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/executions", tags=["executions"])


@router.get(
    "",
    response_model=list[ExecutionSummary],
    dependencies=[Depends(require_scope(SCOPE_EXECUTION_READ))],
    summary="List executions in the current project",
)
async def list_executions(
    workflow_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
) -> list[ExecutionSummary]:
    """Return summary rows (no run-data) matching the filter."""
    entities = await ExecutionRepository(session).list(
        project_id=project_id,
        workflow_id=workflow_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [
        ExecutionSummary(
            id=e.id,
            workflow_id=e.workflow_id,
            mode=e.mode,
            status=e.status,
            started_at=e.started_at,
            finished_at=e.finished_at,
            triggered_by=e.triggered_by,
        )
        for e in entities
    ]


@router.get(
    "/{execution_id}",
    response_model=ExecutionResponse,
    dependencies=[Depends(require_scope(SCOPE_EXECUTION_READ))],
    summary="Fetch a full execution including run-data",
)
async def get_execution(
    execution_id: str,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
) -> ExecutionResponse:
    """Return the execution + per-node run data."""
    execution = await ExecutionRepository(session).get(execution_id, project_id=project_id)
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution not found")
    return execution_to_response(execution)
