"""Async repository for :class:`TriggerScheduleEntity`.

The trigger manager is the only caller. API handlers never reach into this
table directly — they toggle workflow activation and the manager takes care
of the trigger-side bookkeeping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from weftlyflow.db.entities.trigger_schedule import TriggerScheduleEntity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TriggerScheduleRepository:
    """Read/write operations over the ``trigger_schedules`` table."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        """Bind to an :class:`AsyncSession`."""
        self._session = session

    async def create(self, entity: TriggerScheduleEntity) -> TriggerScheduleEntity:
        """Persist a new trigger-schedule row and flush."""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def list_for_workflow(self, workflow_id: str) -> list[TriggerScheduleEntity]:
        """Return every schedule registered under ``workflow_id``."""
        stmt = select(TriggerScheduleEntity).where(
            TriggerScheduleEntity.workflow_id == workflow_id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def list_all(self) -> list[TriggerScheduleEntity]:
        """Return every schedule row — used by the scheduler warm-up on boot."""
        stmt = select(TriggerScheduleEntity)
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def delete_for_workflow(self, workflow_id: str) -> int:
        """Drop every schedule bound to ``workflow_id``. Returns row count."""
        result = await self._session.execute(
            delete(TriggerScheduleEntity).where(
                TriggerScheduleEntity.workflow_id == workflow_id,
            ),
        )
        return int(getattr(result, "rowcount", 0) or 0)
