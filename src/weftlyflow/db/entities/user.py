"""Users — human accounts that authenticate via email + password.

Relationships:
    * Each user belongs to zero-or-more projects through the owner column on
      :class:`ProjectEntity` plus sharing rows (added in Phase 6).
    * Refresh tokens are stored in :mod:`refresh_token` and joined by user id.

A user's password hash is stored here; the raw password is never persisted.
See :mod:`weftlyflow.auth.passwords` for hashing + verification.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from weftlyflow.db.base import Base
from weftlyflow.db.entities.mixins import IdMixin, TimestampMixin


class UserEntity(Base, IdMixin, TimestampMixin):
    """Account row — email is unique, password is argon2id-hashed."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    global_role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")
    default_project_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
