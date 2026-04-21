"""Initial Phase-2 schema — users, projects, workflows, executions, refresh tokens.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all Phase-2 tables."""
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("global_role", sa.String(length=32), nullable=False, server_default="member"),
        sa.Column("default_project_id", sa.String(length=40), nullable=True),
        sa.Column("mfa_secret", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="personal"),
        sa.Column("owner_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "workflows",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("project_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("nodes", sa.JSON(), nullable=False),
        sa.Column("connections", sa.JSON(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("static_data", sa.JSON(), nullable=False),
        sa.Column("pin_data", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version_id", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "executions",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("workflow_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("project_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wait_till", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_by", sa.String(length=120), nullable=True),
    )

    op.create_table(
        "execution_data",
        sa.Column(
            "execution_id",
            sa.String(length=40),
            sa.ForeignKey("executions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("workflow_snapshot", sa.JSON(), nullable=False),
        sa.Column("run_data", sa.JSON(), nullable=False),
        sa.Column("storage_kind", sa.String(length=8), nullable=False, server_default="db"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("user_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Drop every Phase-2 table in reverse creation order."""
    op.drop_table("refresh_tokens")
    op.drop_table("execution_data")
    op.drop_table("executions")
    op.drop_table("workflows")
    op.drop_table("projects")
    op.drop_table("users")
