"""Refresh tokens — revocable, stored as hashes.

Each issued refresh token is recorded here with a SHA-256 digest (never the
raw token). Logout + rotation both delete the matching row, so a leaked token
can be invalidated by admin action without needing a JWT blocklist at the
access-token layer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from weftlyflow.db.base import Base
from weftlyflow.db.entities.mixins import IdMixin


class RefreshTokenEntity(Base, IdMixin):
    """One issued refresh token, stored as an opaque SHA-256 hex digest."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
