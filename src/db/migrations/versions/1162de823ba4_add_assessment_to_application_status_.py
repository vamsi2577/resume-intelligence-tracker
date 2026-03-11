"""add assessment to application_status enum

Revision ID: 1162de823ba4
Revises: 001
Create Date: 2026-03-11 18:49:00.463403
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1162de823ba4'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Explicit connection commit required for ALTER TYPE in postgres
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE application_status ADD VALUE IF NOT EXISTS 'assessment'")


def downgrade() -> None:
    pass
