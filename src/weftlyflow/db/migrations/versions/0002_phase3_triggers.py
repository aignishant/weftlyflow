"""Phase-3 schema — webhooks + trigger_schedules.

Revision ID: 0002_phase3_triggers
Revises: 0001_initial_schema
Create Date: 2026-04-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase3_triggers"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the webhooks + trigger_schedules tables."""
    op.create_table(
        "webhooks",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("workflow_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("node_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("path", sa.String(length=400), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("is_dynamic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "response_mode",
            sa.String(length=24),
            nullable=False,
            server_default="immediately",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("path", "method", name="uq_webhooks_path_method"),
    )

    op.create_table(
        "trigger_schedules",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("workflow_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("node_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("cron_expression", sa.String(length=120), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Drop the tables in reverse creation order."""
    op.drop_table("trigger_schedules")
    op.drop_table("webhooks")
