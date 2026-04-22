"""Workflow CRUD + execute endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status

from weftlyflow.auth.constants import (
    SCOPE_WORKFLOW_EXECUTE,
    SCOPE_WORKFLOW_READ,
    SCOPE_WORKFLOW_WRITE,
)
from weftlyflow.db.repositories.workflow_repo import WorkflowRepository
from weftlyflow.domain.execution import Item
from weftlyflow.engine.executor import WorkflowExecutor
from weftlyflow.server.deps import (
    get_current_project,
    get_db,
    get_registry,
    get_trigger_manager,
    require_scope,
)
from weftlyflow.server.mappers.execution import execution_to_response
from weftlyflow.server.mappers.workflow import (
    workflow_create_to_domain,
    workflow_to_response,
    workflow_update_to_domain,
)
from weftlyflow.server.persistence_hooks import save_execution
from weftlyflow.server.schemas.executions import ExecutionResponse
from weftlyflow.server.schemas.workflows import (
    WorkflowCreateRequest,
    WorkflowExecuteRequest,
    WorkflowResponse,
    WorkflowUpdateRequest,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.nodes.registry import NodeRegistry
    from weftlyflow.triggers.manager import ActiveTriggerManager

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


@router.get(
    "",
    response_model=list[WorkflowResponse],
    dependencies=[Depends(require_scope(SCOPE_WORKFLOW_READ))],
    summary="List workflows in the current project",
)
async def list_workflows(
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    archived: bool = Query(default=False),
) -> list[WorkflowResponse]:
    """Return workflow summaries for the scoped project."""
    workflows = await WorkflowRepository(session).list(
        project_id=project_id, limit=limit, offset=offset, archived=archived,
    )
    return [workflow_to_response(w) for w in workflows]


@router.post(
    "",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope(SCOPE_WORKFLOW_WRITE))],
    summary="Create a workflow",
)
async def create_workflow(
    body: WorkflowCreateRequest,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """Persist a new workflow and return its view."""
    workflow = workflow_create_to_domain(body, project_id=project_id)
    created = await WorkflowRepository(session).create(workflow)
    return workflow_to_response(created)


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    dependencies=[Depends(require_scope(SCOPE_WORKFLOW_READ))],
    summary="Fetch a single workflow",
)
async def get_workflow(
    workflow_id: str,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """Return the workflow or raise 404."""
    workflow = await WorkflowRepository(session).get(workflow_id, project_id=project_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")
    return workflow_to_response(workflow)


@router.put(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    dependencies=[Depends(require_scope(SCOPE_WORKFLOW_WRITE))],
    summary="Replace a workflow's definition",
)
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdateRequest,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """Overwrite an existing workflow row."""
    updated = workflow_update_to_domain(body, workflow_id=workflow_id, project_id=project_id)
    try:
        result = await WorkflowRepository(session).update(updated)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found",
        ) from exc
    return workflow_to_response(result)


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_scope(SCOPE_WORKFLOW_WRITE))],
    summary="Delete a workflow",
)
async def delete_workflow(
    workflow_id: str,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Remove the workflow row."""
    deleted = await WorkflowRepository(session).delete(workflow_id, project_id=project_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")


@router.post(
    "/{workflow_id}/activate",
    response_model=WorkflowResponse,
    dependencies=[Depends(require_scope(SCOPE_WORKFLOW_WRITE))],
    summary="Activate a workflow — register its triggers",
)
async def activate_workflow(
    workflow_id: str,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
    trigger_manager: ActiveTriggerManager = Depends(get_trigger_manager),
) -> WorkflowResponse:
    """Flip ``active=True`` and register every trigger with the trigger manager.

    Activation is idempotent: re-activating an already-active workflow is a
    no-op beyond re-asserting the registrations.
    """
    repo = WorkflowRepository(session)
    workflow = await repo.get(workflow_id, project_id=project_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")

    # Tear down any stale registrations before re-activating so the trigger
    # tables reflect the current workflow definition.
    await trigger_manager.deactivate(workflow)
    result = await trigger_manager.activate(workflow)
    if result.errors:
        await trigger_manager.deactivate(workflow)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "trigger_registration_failed", "errors": result.errors},
        )
    workflow.active = True
    updated = await repo.update(workflow)
    return workflow_to_response(updated)


@router.post(
    "/{workflow_id}/deactivate",
    response_model=WorkflowResponse,
    dependencies=[Depends(require_scope(SCOPE_WORKFLOW_WRITE))],
    summary="Deactivate a workflow — remove its triggers",
)
async def deactivate_workflow(
    workflow_id: str,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
    trigger_manager: ActiveTriggerManager = Depends(get_trigger_manager),
) -> WorkflowResponse:
    """Flip ``active=False`` and tear down every trigger registration."""
    repo = WorkflowRepository(session)
    workflow = await repo.get(workflow_id, project_id=project_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")

    await trigger_manager.deactivate(workflow)
    workflow.active = False
    updated = await repo.update(workflow)
    return workflow_to_response(updated)


@router.post(
    "/{workflow_id}/execute",
    response_model=ExecutionResponse,
    dependencies=[Depends(require_scope(SCOPE_WORKFLOW_EXECUTE))],
    summary="Execute a workflow synchronously and return the run",
)
async def execute_workflow(
    workflow_id: str,
    body: WorkflowExecuteRequest,
    project_id: str = Depends(get_current_project),
    session: AsyncSession = Depends(get_db),
    registry: NodeRegistry = Depends(get_registry),
) -> ExecutionResponse:
    """Load, run, persist, and return the execution.

    Phase 2 executes inline (handler blocks until the workflow finishes). The
    queued execution path via Celery lands in Phase 3.
    """
    workflow = await WorkflowRepository(session).get(workflow_id, project_id=project_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")

    initial_items = [Item(json=dict(payload)) for payload in body.initial_items] or [Item()]
    execution = await WorkflowExecutor(registry).run(
        workflow, initial_items=initial_items, mode="manual",
    )
    await save_execution(session, execution, project_id=project_id)
    return execution_to_response(execution)
