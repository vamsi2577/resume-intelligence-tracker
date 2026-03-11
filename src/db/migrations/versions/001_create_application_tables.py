"""
Migration 001 — create job_applications and application_status_history tables.

Revision ID: 001
Create Date: 2026-03-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Reusable enum type references (create_type=False — we CREATE manually) ──
application_status = ENUM(
    "applied", "screening", "interview", "offer",
    "rejected", "ghosted", "withdrawn",
    name="application_status", create_type=False,
)
application_source = ENUM(
    "manual", "resume_generator",
    name="application_source", create_type=False,
)
work_type = ENUM(
    "remote", "hybrid", "onsite",
    name="work_type", create_type=False,
)


def upgrade() -> None:
    conn = op.get_bind()

    # ── Create enums only if they don't exist ─────────────
    conn.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE application_status AS ENUM (
                'applied', 'screening', 'interview',
                'offer', 'rejected', 'ghosted', 'withdrawn'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))
    conn.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE application_source AS ENUM (
                'manual', 'resume_generator'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))
    conn.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE work_type AS ENUM (
                'remote', 'hybrid', 'onsite'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))

    # ── job_applications ───────────────────────────────────
    op.create_table(
        "job_applications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("job_title", sa.String(255), nullable=False),
        sa.Column("source", application_source, nullable=False),
        sa.Column("status", application_status, nullable=False, server_default="applied"),
        sa.Column("applied_date", sa.Date, nullable=False),
        sa.Column("job_url", sa.Text, nullable=True),
        sa.Column("job_id", sa.String(100), nullable=True),
        sa.Column("resume_version", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("salary_range", sa.String(100), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("work_type", work_type, nullable=True),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("follow_up_date", sa.Date, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_job_applications_company_name", "job_applications", ["company_name"])
    op.create_index("ix_job_applications_status", "job_applications", ["status"])
    op.create_index("ix_job_applications_applied_date", "job_applications", ["applied_date"])
    op.create_index("ix_job_applications_company_job_id", "job_applications", ["company_name", "job_id"])

    # ── application_status_history ─────────────────────────
    op.create_table(
        "application_status_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id", UUID(as_uuid=True),
            sa.ForeignKey("job_applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", application_status, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_status_history_application_id",
        "application_status_history", ["application_id"],
    )


def downgrade() -> None:
    op.drop_table("application_status_history")
    op.drop_table("job_applications")
    conn = op.get_bind()
    conn.execute(sa.text("DROP TYPE IF EXISTS application_status"))
    conn.execute(sa.text("DROP TYPE IF EXISTS application_source"))
    conn.execute(sa.text("DROP TYPE IF EXISTS work_type"))
