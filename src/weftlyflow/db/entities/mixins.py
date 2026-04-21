"""Shared column mixins used across every Weftlyflow entity.

Two axes covered:

* :class:`TimestampMixin` — ``created_at`` / ``updated_at`` columns populated
  by SQLAlchemy defaults + ``onupdate``.
* :class:`IdMixin` — ``id`` primary key typed as ``str`` (prefixed ULID string)
  so Weftlyflow identifiers remain self-describing across databases and log
  lines.

Every concrete entity inherits from :class:`weftlyflow.db.base.Base` and the
mixins it needs. Mixins declare columns via ``Mapped[...]`` + ``mapped_column``
so strict-mypy typing stays intact.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


def _utcnow() -> datetime:
    """Timezone-aware UTC ``now`` — replaces SQLAlchemy's deprecated default."""
    return datetime.now(UTC)


class IdMixin:
    """String primary-key column (prefixed ULID)."""

    id: Mapped[str] = mapped_column(String(40), primary_key=True)


class TimestampMixin:
    """Creation + update timestamps, both UTC-aware."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
