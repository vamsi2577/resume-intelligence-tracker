"""add email_poll_state and email_queue tables

Revision ID: 003_add_email_watcher_tables
Revises: 002_add_needs_review
Create Date: 2026-03-12 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.dialects.postgresql import ENUM

revision: str = '003_add_email_watcher_tables'
down_revision: Union[str, None] = '002_add_needs_review'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

email_queue_status = ENUM(
    'pending',
    'processed',
    'unmatched',
    'failed',
    'ignored',
    name="email_queue_status",
    create_type=False,
)

def upgrade() -> None:
    # ── email_poll_state ──────────────────────────────────
    op.create_table(
        'email_poll_state',
        sa.Column('id', sa.Integer(), nullable=False, default=1),
        sa.Column('last_poll_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── email_queue_status enum ───────────────────────────
    email_queue_status.create(op.get_bind(), checkfirst=True)

    # ── email_queue ───────────────────────────────────────
    op.create_table(
        'email_queue',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('message_id', sa.String(255), nullable=False),
        sa.Column('subject', sa.Text(), nullable=True),
        sa.Column('sender', sa.String(255), nullable=True),
        sa.Column('raw_body', sa.Text(), nullable=True),
        sa.Column('classifier_output', JSONB(), nullable=True),
        sa.Column('status',email_queue_status,nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id'),
    )
    op.create_index('ix_email_queue_status', 'email_queue', ['status'])
    op.create_index('ix_email_queue_message_id', 'email_queue', ['message_id'])


def downgrade() -> None:
    op.drop_table('email_queue')
    op.execute("DROP TYPE IF EXISTS email_queue_status")
    op.drop_table('email_poll_state')
