"""Workflows — persisted definition of a node graph.

``nodes`` and ``connections`` are stored as JSON blobs rather than normalised
tables. Rationale: the editor reads/writes them as a unit, they change
together, and the schema is defined by the Pydantic DTOs. Normalising into
separate rows would buy nothing and invite consistency bugs.

``version_id`` changes on every save and is used for optimistic concurrency.
Workflow history (append-only snapshots) is a separate table added in
Phase 6 when the versioning UI lands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from weftlyflow.db.base import Base
from weftlyflow.db.entities.mixins import IdMixin, TimestampMixin

if TYPE_CHECKING:
    pass


class WorkflowEntity(Base, IdMixin, TimestampMixin):
    """Workflow row — the graph + execution-time settings + activation flag."""

    __tablename__ = "workflows"

    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    nodes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    connections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    static_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    pin_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
