"""Async repository for :class:`WorkflowEntity`.

Every query is **auto-filtered by project_id**. The single exception is the
internal ``_get_raw`` which is used by the executor/persistence hook path —
callers there have already resolved the project scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from weftlyflow.db.entities.workflow import WorkflowEntity
from weftlyflow.db.mappers.workflow import workflow_to_domain, workflow_to_entity_kwargs

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.domain.workflow import Workflow


class WorkflowRepository:
    """Read/write operations over the ``workflows`` table, project-scoped."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        """Bind to an :class:`AsyncSession`."""
        self._session = session

    async def create(self, workflow: Workflow) -> Workflow:
        """Persist a new workflow row."""
        kwargs = workflow_to_entity_kwargs(workflow)
        entity = WorkflowEntity(**kwargs)
        self._session.add(entity)
        await self._session.flush()
        return workflow_to_domain(entity)

    async def get(self, workflow_id: str, *, project_id: str) -> Workflow | None:
        """Return the workflow or ``None`` if it is not in ``project_id``."""
        entity = await self._get_scoped(workflow_id, project_id=project_id)
        return workflow_to_domain(entity) if entity is not None else None

    async def list(
        self,
        *,
        project_id: str,
        archived: bool | None = False,
        active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Workflow]:
        """List workflows in a project with optional filters."""
        stmt = (
            select(WorkflowEntity)
            .where(WorkflowEntity.project_id == project_id)
            .order_by(WorkflowEntity.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if archived is not None:
            stmt = stmt.where(WorkflowEntity.archived == archived)
        if active is not None:
            stmt = stmt.where(WorkflowEntity.active == active)
        result = await self._session.execute(stmt)
        return [workflow_to_domain(entity) for entity in result.scalars()]

    async def update(self, workflow: Workflow) -> Workflow:
        """Overwrite an existing workflow row in place."""
        entity = await self._get_scoped(workflow.id, project_id=workflow.project_id)
        if entity is None:
            msg = f"workflow {workflow.id!r} not found in project {workflow.project_id!r}"
            raise LookupError(msg)
        for key, value in workflow_to_entity_kwargs(workflow).items():
            setattr(entity, key, value)
        await self._session.flush()
        return workflow_to_domain(entity)

    async def delete(self, workflow_id: str, *, project_id: str) -> bool:
        """Hard-delete a workflow (Phase 6 will convert this to soft-delete)."""
        result = await self._session.execute(
            delete(WorkflowEntity).where(
                WorkflowEntity.id == workflow_id,
                WorkflowEntity.project_id == project_id,
            ),
        )
        return bool(getattr(result, "rowcount", 0))

    async def _get_scoped(self, workflow_id: str, *, project_id: str) -> WorkflowEntity | None:
        result = await self._session.execute(
            select(WorkflowEntity).where(
                WorkflowEntity.id == workflow_id,
                WorkflowEntity.project_id == project_id,
            ),
        )
        return result.scalar_one_or_none()
