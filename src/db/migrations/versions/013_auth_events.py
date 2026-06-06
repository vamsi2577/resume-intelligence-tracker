"""add auth_events audit table (Phase 5 auth-hardening)

Revision ID: 013_auth_events
Revises: 012_user_token_version
Create Date: 2026-06-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "013_auth_events"
down_revision: Union[str, None] = "012_user_token_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("detail", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_auth_events_type_created", "auth_events", ["event_type", "created_at"])
    op.create_index("ix_auth_events_user", "auth_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_events_user", table_name="auth_events")
    op.drop_index("ix_auth_events_type_created", table_name="auth_events")
    op.drop_table("auth_events")
