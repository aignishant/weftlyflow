"""Async repository for :class:`ProjectEntity`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from weftlyflow.db.entities.project import ProjectEntity
from weftlyflow.db.mappers.project import project_to_domain

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.auth.views import ProjectView


class ProjectRepository:
    """Queries over the ``projects`` table."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        """Bind to an :class:`AsyncSession`."""
        self._session = session

    async def get_by_id(self, project_id: str) -> ProjectView | None:
        """Return the project row as a :class:`ProjectView`."""
        entity = await self._session.get(ProjectEntity, project_id)
        return project_to_domain(entity) if entity is not None else None

    async def list_for_user(self, user_id: str) -> list[ProjectView]:
        """Return every project owned by ``user_id`` (sharing arrives Phase 6)."""
        result = await self._session.execute(
            select(ProjectEntity).where(ProjectEntity.owner_id == user_id),
        )
        return [project_to_domain(entity) for entity in result.scalars()]

    async def create(
        self,
        *,
        project_id: str,
        name: str,
        kind: str,
        owner_id: str,
    ) -> ProjectView:
        """Insert a new project row."""
        entity = ProjectEntity(id=project_id, name=name, kind=kind, owner_id=owner_id)
        self._session.add(entity)
        await self._session.flush()
        return project_to_domain(entity)
