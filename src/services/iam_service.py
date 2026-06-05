"""
IAM service layer (Phase 1b).

Authorization read/resolve + admin write operations:
  - effective permission / role resolution for a user (direct roles + roles
    conferred via group membership)
  - admin operations on users (list, deactivate, assign/revoke role) that write
    an iam_audit_log row for every privileged change.

Authorization is orthogonal to tenancy: these functions are NOT owner-scoped —
they operate across users by design and are reachable only behind admin
permissions (see require_permission in src/api/deps.py).
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.iam import (
    GroupMember,
    GroupRole,
    IamAuditLog,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from src.models.user import User
from src.utils.exceptions import NotFoundError
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Resolution (read side) ────────────────────────────────

async def get_role_names(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """All role names held by the user — directly and via group membership."""
    direct = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    via_group = (
        select(Role.name)
        .join(GroupRole, GroupRole.role_id == Role.id)
        .join(GroupMember, GroupMember.group_id == GroupRole.group_id)
        .where(GroupMember.user_id == user_id)
    )
    rows = (await db.execute(direct.union(via_group))).all()
    return sorted({r[0] for r in rows})


async def get_effective_permissions(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """The user's effective permission keys: union of permissions granted by
    their direct roles and by roles conferred through group membership."""
    direct = (
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    )
    via_group = (
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(GroupRole, GroupRole.role_id == RolePermission.role_id)
        .join(GroupMember, GroupMember.group_id == GroupRole.group_id)
        .where(GroupMember.user_id == user_id)
    )
    rows = (await db.execute(direct.union(via_group))).all()
    return {r[0] for r in rows}


async def list_roles(db: AsyncSession) -> list[Role]:
    rows = (await db.execute(select(Role).order_by(Role.name))).scalars().all()
    return list(rows)


# ── Admin operations (write side) — all audit-logged ──────

async def _audit(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID,
    action: str,
    target_id: uuid.UUID | None = None,
    detail: dict | None = None,
) -> None:
    db.add(IamAuditLog(
        id=uuid.uuid4(),
        actor_user_id=actor_id,
        action=action,
        target_user_id=target_id,
        detail=detail,
    ))


async def list_users(db: AsyncSession, *, limit: int = 100, offset: int = 0) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(stmt)).scalars().all())


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User", str(user_id))
    return user


async def set_user_active(
    db: AsyncSession, *, actor_id: uuid.UUID, user_id: uuid.UUID, is_active: bool
) -> User:
    user = await get_user(db, user_id)
    user.is_active = is_active
    await _audit(
        db, actor_id=actor_id,
        action="user.activate" if is_active else "user.deactivate",
        target_id=user_id,
    )
    await db.flush()
    await db.refresh(user)
    return user


async def assign_role(
    db: AsyncSession, *, actor_id: uuid.UUID, user_id: uuid.UUID, role_name: str
) -> list[str]:
    await get_user(db, user_id)
    role = (await db.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role", role_name)
    # Idempotent — skip if already assigned.
    existing = (await db.execute(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
    )).scalar_one_or_none()
    if existing is None:
        db.add(UserRole(user_id=user_id, role_id=role.id, granted_by=actor_id))
        await _audit(
            db, actor_id=actor_id, action="role.grant", target_id=user_id,
            detail={"role": role_name},
        )
    await db.flush()
    return await get_role_names(db, user_id)


async def revoke_role(
    db: AsyncSession, *, actor_id: uuid.UUID, user_id: uuid.UUID, role_name: str
) -> list[str]:
    await get_user(db, user_id)
    role = (await db.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role", role_name)
    # Don't let an admin strip their own last admin path by accident — but keep
    # it simple here: just disallow revoking a role the user doesn't have is a
    # no-op; revoking is allowed otherwise.
    await db.execute(
        delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
    )
    await _audit(
        db, actor_id=actor_id, action="role.revoke", target_id=user_id,
        detail={"role": role_name},
    )
    await db.flush()
    return await get_role_names(db, user_id)
