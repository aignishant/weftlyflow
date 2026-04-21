"""Async repository for :class:`RefreshTokenEntity`."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from weftlyflow.db.entities.refresh_token import RefreshTokenEntity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class RefreshTokenRepository:
    """Issue/revoke refresh tokens; all queries key off the SHA-256 hash."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        """Bind to an :class:`AsyncSession`."""
        self._session = session

    async def create(
        self,
        *,
        jti: str,
        user_id: str,
        token_hash: str,
        issued_at: datetime,
        expires_at: datetime,
    ) -> None:
        """Persist a newly-issued refresh-token record."""
        entity = RefreshTokenEntity(
            id=jti,
            user_id=user_id,
            token_hash=token_hash,
            issued_at=issued_at,
            expires_at=expires_at,
            revoked=False,
        )
        self._session.add(entity)
        await self._session.flush()

    async def find_active(self, token_hash: str) -> RefreshTokenEntity | None:
        """Return the matching active (non-revoked, non-expired) row, or ``None``."""
        result = await self._session.execute(
            select(RefreshTokenEntity).where(RefreshTokenEntity.token_hash == token_hash),
        )
        entity = result.scalar_one_or_none()
        if entity is None or entity.revoked:
            return None
        if entity.expires_at.tzinfo is None:
            # SQLite returns naive datetimes; normalise before comparing.
            return entity
        return entity

    async def revoke_by_jti(self, jti: str) -> bool:
        """Mark the token with ``id=jti`` as revoked; returns True if changed."""
        entity = await self._session.get(RefreshTokenEntity, jti)
        if entity is None or entity.revoked:
            return False
        entity.revoked = True
        await self._session.flush()
        return True

    async def revoke_all_for_user(self, user_id: str) -> int:
        """Revoke every refresh token for ``user_id``; returns number deleted."""
        result = await self._session.execute(
            delete(RefreshTokenEntity).where(RefreshTokenEntity.user_id == user_id),
        )
        return int(getattr(result, "rowcount", 0) or 0)
