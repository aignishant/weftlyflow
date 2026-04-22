"""Webhooks — persisted ingress routes registered by webhook-trigger nodes.

One row per active webhook. The combination ``(path, method)`` is globally
unique: activating a second workflow on the same pair is rejected at the
registry layer before hitting the database constraint.

``path`` is stored **without** a leading slash to keep lookups reversible —
the ingress router strips it too.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from weftlyflow.db.base import Base
from weftlyflow.db.entities.mixins import IdMixin, TimestampMixin


class WebhookEntity(Base, IdMixin, TimestampMixin):
    """Active-webhook row — reverse index from ``(path, method)`` to node."""

    __tablename__ = "webhooks"
    __table_args__ = (UniqueConstraint("path", "method", name="uq_webhooks_path_method"),)

    workflow_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(40), nullable=False)
    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(400), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    is_dynamic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    response_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, default="immediately",
    )
