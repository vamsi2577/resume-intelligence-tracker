"""add users table and owner_id FK on data tables

Phase 1 multi-tenancy: introduce the `users` table as the root of ownership,
seed a single default tenant (settings.DEFAULT_OWNER_ID), backfill every
existing row to it, and make owner_id a NOT NULL FK on job_applications,
base_resumes, and resume_generations.

Non-breaking: owner_id carries a server_default of the default owner so
existing insert paths keep working until Phase 2 threads a real owner_id.

Revision ID: 008_users_owner_id
Revises: 007_add_resume_generations
Create Date: 2026-06-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# Keep <= 32 chars (alembic_version.version_num is VARCHAR(32)).
revision: str = "008_users_owner_id"
down_revision: Union[str, None] = "007_add_resume_generations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed seed identity for the single Phase-1 tenant (matches
# settings.DEFAULT_OWNER_ID). Hard-coded here so the migration is
# self-contained and independent of runtime config.
DEFAULT_OWNER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # 1. users table -------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    # Case-insensitive unique email.
    op.create_index(
        "ux_users_email", "users", [sa.text("lower(email)")], unique=True
    )

    # 2. seed the default tenant ------------------------------------------
    op.execute(
        sa.text(
            "INSERT INTO users (id, email, is_active, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), :email, true, now(), now())"
        ).bindparams(id=DEFAULT_OWNER_ID, email="default_owner@local")
    )

    # 3. job_applications.owner_id (NEW column) ---------------------------
    # server_default backfills existing rows in the same statement.
    op.add_column(
        "job_applications",
        sa.Column(
            "owner_id", UUID(as_uuid=True), nullable=False,
            server_default=DEFAULT_OWNER_ID,
        ),
    )

    # 4. base_resumes / resume_generations.owner_id (existing nullable cols)
    for table in ("base_resumes", "resume_generations"):
        op.execute(
            sa.text(
                f"UPDATE {table} SET owner_id = CAST(:owner AS uuid) WHERE owner_id IS NULL"
            ).bindparams(owner=DEFAULT_OWNER_ID)
        )
        op.alter_column(
            table, "owner_id",
            existing_type=UUID(as_uuid=True),
            nullable=False,
            server_default=DEFAULT_OWNER_ID,
        )

    # 5. FK constraints (owner_id -> users.id, CASCADE) -------------------
    op.create_foreign_key(
        "fk_job_applications_owner", "job_applications", "users",
        ["owner_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_base_resumes_owner", "base_resumes", "users",
        ["owner_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_resume_generations_owner", "resume_generations", "users",
        ["owner_id"], ["id"], ondelete="CASCADE",
    )

    # 6. indexes ----------------------------------------------------------
    op.create_index("ix_job_applications_owner_id", "job_applications", ["owner_id"])
    op.create_index(
        "ix_job_applications_owner_active_date", "job_applications",
        ["owner_id", "is_deleted", "applied_date"],
    )
    # Dedup detection becomes per-owner: drop the old (company, job_id) index
    # and recreate it scoped by owner.
    op.drop_index("ix_job_applications_company_job_id", table_name="job_applications")
    op.create_index(
        "ix_job_applications_owner_company_job_id", "job_applications",
        ["owner_id", "company_name", "job_id"],
    )
    op.create_index(
        "ix_resume_generations_owner_created", "resume_generations",
        ["owner_id", "created_at"],
    )


def downgrade() -> None:
    # Reverse of upgrade, preserving columns that pre-existed (base_resumes
    # and resume_generations owner_id existed nullable before this migration).
    op.drop_index("ix_resume_generations_owner_created", table_name="resume_generations")
    op.drop_index("ix_job_applications_owner_company_job_id", table_name="job_applications")
    op.create_index(
        "ix_job_applications_company_job_id", "job_applications",
        ["company_name", "job_id"],
    )
    op.drop_index("ix_job_applications_owner_active_date", table_name="job_applications")
    op.drop_index("ix_job_applications_owner_id", table_name="job_applications")

    op.drop_constraint("fk_resume_generations_owner", "resume_generations", type_="foreignkey")
    op.drop_constraint("fk_base_resumes_owner", "base_resumes", type_="foreignkey")
    op.drop_constraint("fk_job_applications_owner", "job_applications", type_="foreignkey")

    # job_applications.owner_id was new in this migration → drop it.
    op.drop_column("job_applications", "owner_id")

    # Restore the pre-008 nullable state on the two pre-existing columns.
    for table in ("base_resumes", "resume_generations"):
        op.alter_column(
            table, "owner_id",
            existing_type=UUID(as_uuid=True),
            nullable=True,
            server_default=None,
        )

    op.execute(
        sa.text("DELETE FROM users WHERE id = CAST(:id AS uuid)").bindparams(id=DEFAULT_OWNER_ID)
    )
    op.drop_index("ux_users_email", table_name="users")
    op.drop_table("users")
