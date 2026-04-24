"""Async repository for :class:`ExecutionEntity` + :class:`ExecutionDataEntity`.

The two tables are written together — there is no valid execution row without
run-data, so :meth:`save` always upserts both. The bulky payload is routed
through an :class:`~weftlyflow.db.execution_storage.ExecutionDataStore`; the
default is DB inlining but operators can opt into filesystem/object-store
backends without the repository caring where bytes actually land.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from weftlyflow.db.entities.execution import ExecutionEntity
from weftlyflow.db.entities.execution_data import ExecutionDataEntity
from weftlyflow.db.execution_storage import (
    ExecutionDataStore,
    StoredDataRow,
    get_default_store,
)
from weftlyflow.db.mappers.execution import (
    execution_to_domain,
    execution_to_entity_kwargs,
    execution_to_payload,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.domain.execution import Execution


class ExecutionRepository:
    """Reads + writes the execution pair, project-scoped on reads."""

    __slots__ = ("_data_store", "_session")

    def __init__(
        self,
        session: AsyncSession,
        *,
        data_store: ExecutionDataStore | None = None,
    ) -> None:
        """Bind to an :class:`AsyncSession` and a data store.

        Args:
            session: The live async session.
            data_store: The store used for the bulky
                ``workflow_snapshot`` + ``run_data`` pair. ``None`` uses the
                process-wide default built from settings.
        """
        self._session = session
        self._data_store = data_store if data_store is not None else get_default_store()

    async def save(self, execution: Execution, *, project_id: str) -> Execution:
        """Upsert both rows for ``execution`` and return it unchanged."""
        entity = await self._session.get(ExecutionEntity, execution.id)
        meta_kwargs = execution_to_entity_kwargs(execution, project_id=project_id)
        if entity is None:
            self._session.add(ExecutionEntity(**meta_kwargs))
        else:
            for key, value in meta_kwargs.items():
                setattr(entity, key, value)

        payload = execution_to_payload(execution)
        stored = await self._data_store.write(execution.id, payload)

        data = await self._session.get(ExecutionDataEntity, execution.id)
        if data is None:
            self._session.add(
                ExecutionDataEntity(
                    execution_id=execution.id,
                    workflow_snapshot=stored.workflow_snapshot,
                    run_data=stored.run_data,
                    storage_kind=stored.storage_kind,
                    external_ref=stored.external_ref,
                ),
            )
        else:
            data.workflow_snapshot = stored.workflow_snapshot
            data.run_data = stored.run_data
            data.storage_kind = stored.storage_kind
            data.external_ref = stored.external_ref

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
        stored_row = StoredDataRow(
            storage_kind=data.storage_kind,
            external_ref=data.external_ref,
            workflow_snapshot=data.workflow_snapshot,
            run_data=data.run_data,
        )
        payload = await self._data_store.read(execution_id, stored_row)
        return execution_to_domain(entity, payload, data_storage=data.storage_kind)

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
