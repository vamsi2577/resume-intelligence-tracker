"""add IAM / RBAC tables and seed roles + permissions

Phase 1b: roles, permissions, groups (cohorts), their many-to-many links, and
the IAM audit log. Seeds the permission catalog + 4 built-in roles + the
role->permission map, and grants the default owner the superadmin role so
admin is ready when auth (Phase 2) lands.

Authorization is orthogonal to tenancy — none of these tables carry a data
owner_id.

Revision ID: 009_iam_rbac
Revises: 008_users_owner_id
Create Date: 2026-06-05 00:00:00.000000
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.core.permissions import (
    DEFAULT_OWNER_ROLES,
    PERMISSION_CATALOG,
    ROLE_PERMISSIONS,
    SYSTEM_ROLES,
)


revision: str = "009_iam_rbac"
down_revision: Union[str, None] = "008_users_owner_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_OWNER_ID = "00000000-0000-0000-0000-000000000001"


def _timestamps() -> list[sa.Column]:
    now = sa.text("now()")
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    ]


def upgrade() -> None:
    # ── Tables ────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        *_timestamps(),
    )
    op.create_table(
        "permissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        *_timestamps(),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", UUID(as_uuid=True),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", UUID(as_uuid=True),
                  sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
        *_timestamps(),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", UUID(as_uuid=True),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("granted_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
    )
    op.create_table(
        "groups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
    )
    op.create_table(
        "group_members",
        sa.Column("group_id", UUID(as_uuid=True),
                  sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("added_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
    )
    op.create_table(
        "group_roles",
        sa.Column("group_id", UUID(as_uuid=True),
                  sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", UUID(as_uuid=True),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        *_timestamps(),
    )
    op.create_table(
        "iam_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("detail", JSONB(), nullable=True),
        *_timestamps(),
    )

    op.create_index("ix_user_roles_user", "user_roles", ["user_id"])
    op.create_index("ix_group_members_user", "group_members", ["user_id"])
    op.create_index("ix_iam_audit_actor", "iam_audit_log", ["actor_user_id", "created_at"])

    # ── Seed: permissions ─────────────────────────────────
    perm_ids: dict[str, uuid.UUID] = {}
    for key, category, description in PERMISSION_CATALOG:
        pid = uuid.uuid4()
        perm_ids[key] = pid
        op.execute(
            sa.text(
                "INSERT INTO permissions (id, key, description, category, created_at, updated_at) "
                "VALUES (:id, :key, :description, :category, now(), now())"
            ).bindparams(id=pid, key=key, description=description, category=category)
        )

    # ── Seed: roles ───────────────────────────────────────
    role_ids: dict[str, uuid.UUID] = {}
    for name, description in SYSTEM_ROLES:
        rid = uuid.uuid4()
        role_ids[name] = rid
        op.execute(
            sa.text(
                "INSERT INTO roles (id, name, description, is_system, created_at, updated_at) "
                "VALUES (:id, :name, :description, true, now(), now())"
            ).bindparams(id=rid, name=name, description=description)
        )

    # ── Seed: role -> permission map ──────────────────────
    for role_name, perm_keys in ROLE_PERMISSIONS.items():
        for key in perm_keys:
            op.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
                    "VALUES (:rid, :pid, now(), now())"
                ).bindparams(rid=role_ids[role_name], pid=perm_ids[key])
            )

    # ── Seed: grant the default owner its roles (user + superadmin) ──
    for role_name in DEFAULT_OWNER_ROLES:
        op.execute(
            sa.text(
                "INSERT INTO user_roles (user_id, role_id, granted_at, created_at, updated_at) "
                "VALUES (CAST(:uid AS uuid), :rid, now(), now(), now())"
            ).bindparams(uid=DEFAULT_OWNER_ID, rid=role_ids[role_name])
        )


def downgrade() -> None:
    op.drop_index("ix_iam_audit_actor", table_name="iam_audit_log")
    op.drop_index("ix_group_members_user", table_name="group_members")
    op.drop_index("ix_user_roles_user", table_name="user_roles")
    op.drop_table("iam_audit_log")
    op.drop_table("group_roles")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
