"""add needs_review to job_applications

Revision ID: 002_add_needs_review
Revises: 1162de823ba4
Create Date: 2026-03-12 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002_add_needs_review'
down_revision: Union[str, None] = '1162de823ba4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'job_applications',
        sa.Column('needs_review', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade() -> None:
    op.drop_column('job_applications', 'needs_review')
