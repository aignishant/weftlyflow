"""Workflow DTO ↔ domain mapper."""

from __future__ import annotations

from typing import TYPE_CHECKING

from weftlyflow.domain.ids import new_workflow_id
from weftlyflow.domain.workflow import (
    Connection,
    Node,
    RetryPolicy,
    Workflow,
    WorkflowSettings,
)
from weftlyflow.server.schemas.workflows import (
    ConnectionDTO,
    NodeDTO,
    RetryPolicyDTO,
    WorkflowCreateRequest,
    WorkflowResponse,
    WorkflowSettingsDTO,
    WorkflowUpdateRequest,
)

if TYPE_CHECKING:
    pass


def workflow_create_to_domain(body: WorkflowCreateRequest, *, project_id: str) -> Workflow:
    """Build a brand-new :class:`Workflow` from the POST payload."""
    return Workflow(
        id=new_workflow_id(),
        project_id=project_id,
        name=body.name,
        nodes=[_node_from_dto(n) for n in body.nodes],
        connections=[_connection_from_dto(c) for c in body.connections],
        settings=_settings_from_dto(body.settings),
        tags=list(body.tags),
    )


def workflow_update_to_domain(
    body: WorkflowUpdateRequest,
    *,
    workflow_id: str,
    project_id: str,
    version_id: str | None = None,
) -> Workflow:
    """Build a full :class:`Workflow` for an update (id + project preserved)."""
    return Workflow(
        id=workflow_id,
        project_id=project_id,
        name=body.name,
        nodes=[_node_from_dto(n) for n in body.nodes],
        connections=[_connection_from_dto(c) for c in body.connections],
        settings=_settings_from_dto(body.settings),
        tags=list(body.tags),
        active=body.active,
        archived=body.archived,
        version_id=version_id,
    )


def workflow_to_response(workflow: Workflow) -> WorkflowResponse:
    """Project a :class:`Workflow` onto the wire format."""
    return WorkflowResponse(
        id=workflow.id,
        project_id=workflow.project_id,
        name=workflow.name,
        nodes=[_node_to_dto(n) for n in workflow.nodes],
        connections=[_connection_to_dto(c) for c in workflow.connections],
        settings=_settings_to_dto(workflow.settings),
        tags=list(workflow.tags),
        active=workflow.active,
        archived=workflow.archived,
    )


def _node_from_dto(dto: NodeDTO) -> Node:
    retry = _retry_from_dto(dto.retry_policy) if dto.retry_policy is not None else None
    position = (
        (dto.position[0], dto.position[1])
        if len(dto.position) >= _POSITION_LEN
        else (0.0, 0.0)
    )
    return Node(
        id=dto.id,
        name=dto.name,
        type=dto.type,
        type_version=dto.type_version,
        parameters=dict(dto.parameters),
        credentials=dict(dto.credentials),
        position=position,
        disabled=dto.disabled,
        notes=dto.notes,
        continue_on_fail=dto.continue_on_fail,
        retry_policy=retry,
    )


_POSITION_LEN = 2


def _node_to_dto(node: Node) -> NodeDTO:
    return NodeDTO(
        id=node.id,
        name=node.name,
        type=node.type,
        type_version=node.type_version,
        parameters=dict(node.parameters),
        credentials=dict(node.credentials),
        position=[node.position[0], node.position[1]],
        disabled=node.disabled,
        notes=node.notes,
        continue_on_fail=node.continue_on_fail,
        retry_policy=_retry_to_dto(node.retry_policy) if node.retry_policy is not None else None,
    )


def _connection_from_dto(dto: ConnectionDTO) -> Connection:
    return Connection(
        source_node=dto.source_node,
        target_node=dto.target_node,
        source_port=dto.source_port,
        source_index=dto.source_index,
        target_port=dto.target_port,
        target_index=dto.target_index,
    )


def _connection_to_dto(conn: Connection) -> ConnectionDTO:
    return ConnectionDTO(
        source_node=conn.source_node,
        target_node=conn.target_node,
        source_port=conn.source_port,
        source_index=conn.source_index,
        target_port=conn.target_port,
        target_index=conn.target_index,
    )


def _settings_from_dto(dto: WorkflowSettingsDTO) -> WorkflowSettings:
    return WorkflowSettings(
        timezone=dto.timezone,
        timeout_seconds=dto.timeout_seconds,
        save_manual_executions=dto.save_manual_executions,
        save_trigger_executions_on=dto.save_trigger_executions_on,  # type: ignore[arg-type]
        error_workflow_id=dto.error_workflow_id,
        caller_policy=dto.caller_policy,  # type: ignore[arg-type]
    )


def _settings_to_dto(settings: WorkflowSettings) -> WorkflowSettingsDTO:
    return WorkflowSettingsDTO(
        timezone=settings.timezone,
        timeout_seconds=settings.timeout_seconds,
        save_manual_executions=settings.save_manual_executions,
        save_trigger_executions_on=settings.save_trigger_executions_on,
        error_workflow_id=settings.error_workflow_id,
        caller_policy=settings.caller_policy,
    )


def _retry_from_dto(dto: RetryPolicyDTO) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=dto.max_attempts,
        backoff_factor=dto.backoff_factor,
        base_delay_ms=dto.base_delay_ms,
        max_delay_ms=dto.max_delay_ms,
    )


def _retry_to_dto(retry: RetryPolicy) -> RetryPolicyDTO:
    return RetryPolicyDTO(
        max_attempts=retry.max_attempts,
        backoff_factor=retry.backoff_factor,
        base_delay_ms=retry.base_delay_ms,
        max_delay_ms=retry.max_delay_ms,
    )
