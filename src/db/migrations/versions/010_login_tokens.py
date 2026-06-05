"""add login_tokens table (Phase 2 magic-link auth)

Revision ID: 010_login_tokens
Revises: 009_iam_rbac
Create Date: 2026-06-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "010_login_tokens"
down_revision: Union[str, None] = "009_iam_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_login_tokens_email", "login_tokens", ["email"])


def downgrade() -> None:
    op.drop_index("ix_login_tokens_email", table_name="login_tokens")
    op.drop_table("login_tokens")
