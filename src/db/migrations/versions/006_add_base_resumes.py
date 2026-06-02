"""add base_resumes table

Revision ID: 006_add_base_resumes
Revises: 005_add_is_deleted
Create Date: 2026-05-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "006_add_base_resumes"
down_revision: Union[str, None] = "005_add_is_deleted"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "base_resumes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=True, unique=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("structured_json", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_base_resumes_owner_id", "base_resumes", ["owner_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_base_resumes_owner_id", table_name="base_resumes")
    op.drop_table("base_resumes")
