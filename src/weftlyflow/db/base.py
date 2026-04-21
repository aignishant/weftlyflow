"""SQLAlchemy declarative base for Weftlyflow entities.

Every table entity in :mod:`weftlyflow.db.entities` inherits from :class:`Base`.
No business logic is allowed on these classes beyond trivial computed columns.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Weftlyflow declarative base.

    Uses SQLAlchemy 2.x typed ``Mapped[...]`` style exclusively. All entities
    declare their columns via ``mapped_column(...)`` rather than legacy
    ``Column(...)`` syntax.
    """
