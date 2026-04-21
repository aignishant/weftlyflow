"""Projects — the multi-tenancy root.

Every workflow and credential belongs to exactly one project. The repository
layer auto-filters every query by ``project_id`` so cross-project leakage is
structurally impossible.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from weftlyflow.db.base import Base
from weftlyflow.db.entities.mixins import IdMixin, TimestampMixin


class ProjectEntity(Base, IdMixin, TimestampMixin):
    """Project row — owner_id points at the creator; membership is separate."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="personal")
    owner_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
