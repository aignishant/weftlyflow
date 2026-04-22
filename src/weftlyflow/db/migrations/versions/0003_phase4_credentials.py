"""Phase-4 schema — credentials + oauth_states.

Revision ID: 0003_phase4_credentials
Revises: 0002_phase3_triggers
Create Date: 2026-04-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase4_credentials"
down_revision: str | None = "0002_phase3_triggers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create credentials + oauth_states."""
    op.create_table(
        "credentials",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("project_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False, index=True),
        sa.Column("data_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "oauth_states",
        sa.Column("state", sa.String(length=64), primary_key=True),
        sa.Column("credential_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("project_id", sa.String(length=40), nullable=False, index=True),
        sa.Column("redirect_uri", sa.String(length=400), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Drop the tables in reverse creation order."""
    op.drop_table("oauth_states")
    op.drop_table("credentials")
