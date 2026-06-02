"""add job_description and resume_content to job_applications

Revision ID: 004_add_resume_generator_fields
Revises: 003_add_email_watcher_tables
Create Date: 2026-03-13 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '004_add_resume_generator_fields'
down_revision: Union[str, None] = '003_add_email_watcher_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'job_applications',
        sa.Column('job_description', sa.Text(), nullable=True)
    )
    op.add_column(
        'job_applications',
        sa.Column('resume_content', JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('job_applications', 'resume_content')
    op.drop_column('job_applications', 'job_description')
