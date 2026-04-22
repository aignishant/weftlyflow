"""Async repository for :class:`CredentialEntity`.

Every query is project-scoped. Plaintext never enters this module — the
caller encrypts before ``save`` and decrypts after ``get``. That split
keeps the cipher a single well-audited boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from weftlyflow.db.entities.credential import CredentialEntity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class CredentialRepository:
    """Read/write operations over the ``credentials`` table, project-scoped."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        """Bind to an :class:`AsyncSession`."""
        self._session = session

    async def create(self, entity: CredentialEntity) -> CredentialEntity:
        """Persist a new credential row; returns the attached entity."""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def get(self, credential_id: str, *, project_id: str) -> CredentialEntity | None:
        """Return the credential scoped to ``project_id`` or ``None``."""
        entity = await self._session.get(CredentialEntity, credential_id)
        if entity is None or entity.project_id != project_id:
            return None
        return entity

    async def list(
        self,
        *,
        project_id: str,
        type_slug: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CredentialEntity]:
        """Return credentials within a project, optionally filtered by type."""
        stmt = (
            select(CredentialEntity)
            .where(CredentialEntity.project_id == project_id)
            .order_by(CredentialEntity.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if type_slug is not None:
            stmt = stmt.where(CredentialEntity.type == type_slug)
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def update(self, entity: CredentialEntity) -> CredentialEntity:
        """Flush pending changes on an attached entity; returns it."""
        await self._session.flush()
        return entity

    async def delete(self, credential_id: str, *, project_id: str) -> bool:
        """Hard-delete the credential; returns True if a row was removed."""
        result = await self._session.execute(
            delete(CredentialEntity).where(
                CredentialEntity.id == credential_id,
                CredentialEntity.project_id == project_id,
            ),
        )
        return bool(getattr(result, "rowcount", 0))
