"""add resume_generations audit table

Revision ID: 007_add_resume_generations
Revises: 006_add_base_resumes
Create Date: 2026-06-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "007_add_resume_generations"
down_revision: Union[str, None] = "006_add_base_resumes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resume_generations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("target_company", sa.String(255), nullable=True),
        sa.Column("job_title", sa.String(255), nullable=True),
        sa.Column("jd_chars", sa.Integer(), nullable=True),
        sa.Column("preview", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("application_id", UUID(as_uuid=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("llm_raw_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_resume_generations_created_at", "resume_generations", ["created_at"]
    )
    op.create_index(
        "ix_resume_generations_status", "resume_generations", ["status"]
    )
    op.create_index(
        "ix_resume_generations_correlation_id", "resume_generations", ["correlation_id"]
    )
    op.create_index(
        "ix_resume_generations_application_id", "resume_generations", ["application_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_resume_generations_application_id", table_name="resume_generations")
    op.drop_index("ix_resume_generations_correlation_id", table_name="resume_generations")
    op.drop_index("ix_resume_generations_status", table_name="resume_generations")
    op.drop_index("ix_resume_generations_created_at", table_name="resume_generations")
    op.drop_table("resume_generations")
