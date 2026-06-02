"""add is_deleted to job_applications

Revision ID: 005_add_is_deleted
Revises: 004_add_resume_generator_fields
Create Date: 2026-05-19 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '005_add_is_deleted'
down_revision: Union[str, None] = '004_add_resume_generator_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'job_applications',
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false')
    )
    op.create_index('ix_job_applications_is_deleted', 'job_applications', ['is_deleted'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_job_applications_is_deleted', table_name='job_applications')
    op.drop_column('job_applications', 'is_deleted')
