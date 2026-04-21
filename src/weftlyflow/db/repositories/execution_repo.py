"""Async repository for :class:`ExecutionEntity` + :class:`ExecutionDataEntity`.

The two tables are written together — there is no valid execution row without
run-data, so :meth:`save` always upserts both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from weftlyflow.db.entities.execution import ExecutionEntity
from weftlyflow.db.entities.execution_data import ExecutionDataEntity
from weftlyflow.db.mappers.execution import (
    execution_to_data_payload,
    execution_to_domain,
    execution_to_entity_kwargs,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.domain.execution import Execution


class ExecutionRepository:
    """Reads + writes the execution pair, project-scoped on reads."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        """Bind to an :class:`AsyncSession`."""
        self._session = session

    async def save(self, execution: Execution, *, project_id: str) -> Execution:
        """Upsert both rows for ``execution`` and return it unchanged."""
        entity = await self._session.get(ExecutionEntity, execution.id)
        meta_kwargs = execution_to_entity_kwargs(execution, project_id=project_id)
        if entity is None:
            self._session.add(ExecutionEntity(**meta_kwargs))
        else:
            for key, value in meta_kwargs.items():
                setattr(entity, key, value)

        data = await self._session.get(ExecutionDataEntity, execution.id)
        data_payload = execution_to_data_payload(execution)
        if data is None:
            self._session.add(ExecutionDataEntity(**data_payload))
        else:
            for key, value in data_payload.items():
                setattr(data, key, value)

        await self._session.flush()
        return execution

    async def get(self, execution_id: str, *, project_id: str) -> Execution | None:
        """Return the execution or ``None`` if not in ``project_id``."""
        entity = await self._session.get(ExecutionEntity, execution_id)
        if entity is None or entity.project_id != project_id:
            return None
        data = await self._session.get(ExecutionDataEntity, execution_id)
        if data is None:
            return None
        return execution_to_domain(entity, data)

    async def list(
        self,
        *,
        project_id: str,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ExecutionEntity]:
        """Return execution *metadata* rows (without the bulky data sidecar).

        The route that lists executions does not need run-data — callers that
        need the full execution should call :meth:`get` for the one they care
        about.
        """
        stmt = (
            select(ExecutionEntity)
            .where(ExecutionEntity.project_id == project_id)
            .order_by(ExecutionEntity.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if workflow_id is not None:
            stmt = stmt.where(ExecutionEntity.workflow_id == workflow_id)
        if status is not None:
            stmt = stmt.where(ExecutionEntity.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars())
