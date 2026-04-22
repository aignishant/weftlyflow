"""Async repository for :class:`OAuthStateEntity`.

Used only by the OAuth2 handshake routes. Every row is short-lived (10
minutes by default) and is deleted immediately after the ``state`` token
is redeemed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete

from weftlyflow.db.entities.oauth_state import OAuthStateEntity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class OAuthStateRepository:
    """CRUD over the ``oauth_states`` table."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        """Bind to an :class:`AsyncSession`."""
        self._session = session

    async def create(self, entity: OAuthStateEntity) -> OAuthStateEntity:
        """Persist the state token and flush."""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def get(self, state: str) -> OAuthStateEntity | None:
        """Return the state row or ``None``. Does not check expiry."""
        return await self._session.get(OAuthStateEntity, state)

    async def consume(self, state: str) -> OAuthStateEntity | None:
        """Fetch + delete the state row atomically; returns ``None`` if missing or expired."""
        entity = await self._session.get(OAuthStateEntity, state)
        if entity is None:
            return None
        if entity.expires_at < datetime.now(UTC):
            await self._session.delete(entity)
            await self._session.flush()
            return None
        await self._session.delete(entity)
        await self._session.flush()
        return entity

    async def purge_expired(self) -> int:
        """Remove every expired row; returns the number deleted."""
        result = await self._session.execute(
            delete(OAuthStateEntity).where(
                OAuthStateEntity.expires_at < datetime.now(UTC),
            ),
        )
        return int(getattr(result, "rowcount", 0) or 0)
