"""
Admin / IAM management routes (Phase 1b).

  GET    /api/v1/admin/users                      list users           [users.manage]
  GET    /api/v1/admin/users/{id}                 user + roles         [users.manage]
  POST   /api/v1/admin/users/{id}/deactivate      soft-disable account [users.manage]
  POST   /api/v1/admin/users/{id}/activate        re-enable account    [users.manage]
  POST   /api/v1/admin/users/{id}/roles           assign a role        [users.manage]
  DELETE /api/v1/admin/users/{id}/roles/{role}    revoke a role        [users.manage]
  GET    /api/v1/admin/roles                       list roles           [roles.manage]

These deliberately operate ACROSS tenants (not owner-scoped) — they're reachable
only behind admin permissions, and every write is recorded in iam_audit_log by
the service. The `actor_id` returned from require_permission is the admin
performing the action.

Hard-delete of a user (GDPR erasure) is Phase 5; here we only deactivate.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_permission
from src.core.permissions import Permissions
from src.db.session import get_db
from src.schemas.iam import (
    AddMemberRequest,
    AdminUserDetailResponse,
    AdminUserResponse,
    AssignRoleRequest,
    CreateGroupRequest,
    GroupDetailResponse,
    GroupMembersResponse,
    GroupResponse,
    GroupRoleRequest,
    GroupRolesResponse,
    RoleResponse,
    RolesResponse,
)
from src.services import iam_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ── Users ─────────────────────────────────────────────────

@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _actor: uuid.UUID = Depends(require_permission(Permissions.USERS_MANAGE)),
):
    users = await iam_service.list_users(db, limit=limit, offset=offset)
    return [AdminUserResponse.model_validate(u) for u in users]


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _actor: uuid.UUID = Depends(require_permission(Permissions.USERS_MANAGE)),
):
    user = await iam_service.get_user(db, user_id)
    roles = await iam_service.get_role_names(db, user_id)
    resp = AdminUserDetailResponse.model_validate(user)
    resp.roles = roles
    return resp


@router.post("/users/{user_id}/deactivate", response_model=AdminUserResponse)
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID = Depends(require_permission(Permissions.USERS_MANAGE)),
):
    user = await iam_service.set_user_active(db, actor_id=actor, user_id=user_id, is_active=False)
    return AdminUserResponse.model_validate(user)


@router.post("/users/{user_id}/activate", response_model=AdminUserResponse)
async def activate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID = Depends(require_permission(Permissions.USERS_MANAGE)),
):
    user = await iam_service.set_user_active(db, actor_id=actor, user_id=user_id, is_active=True)
    return AdminUserResponse.model_validate(user)


@router.post(
    "/users/{user_id}/roles",
    response_model=RolesResponse,
    status_code=status.HTTP_200_OK,
)
async def assign_role(
    user_id: uuid.UUID,
    body: AssignRoleRequest,
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID = Depends(require_permission(Permissions.USERS_MANAGE)),
):
    roles = await iam_service.assign_role(db, actor_id=actor, user_id=user_id, role_name=body.role)
    return RolesResponse(user_id=user_id, roles=roles)


@router.delete("/users/{user_id}/roles/{role}", response_model=RolesResponse)
async def revoke_role(
    user_id: uuid.UUID,
    role: str,
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID = Depends(require_permission(Permissions.USERS_MANAGE)),
):
    roles = await iam_service.revoke_role(db, actor_id=actor, user_id=user_id, role_name=role)
    return RolesResponse(user_id=user_id, roles=roles)


# ── Roles ─────────────────────────────────────────────────

@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _actor: uuid.UUID = Depends(require_permission(Permissions.ROLES_MANAGE)),
):
    roles = await iam_service.list_roles(db)
    return [RoleResponse.model_validate(r) for r in roles]


# ── Groups (cohorts) — all behind groups.manage ───────────

@router.get("/groups", response_model=list[GroupResponse])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    _actor: uuid.UUID = Depends(require_permission(Permissions.GROUPS_MANAGE)),
):
    groups = await iam_service.list_groups(db)
    return [GroupResponse.model_validate(g) for g in groups]


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: CreateGroupRequest,
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID = Depends(require_permission(Permissions.GROUPS_MANAGE)),
):
    group = await iam_service.create_group(
        db, actor_id=actor, name=body.name, description=body.description
    )
    return GroupResponse.model_validate(group)


@router.get("/groups/{group_id}", response_model=GroupDetailResponse)
async def get_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _actor: uuid.UUID = Depends(require_permission(Permissions.GROUPS_MANAGE)),
):
    group = await iam_service.get_group_required(db, group_id)
    resp = GroupDetailResponse.model_validate(group)
    # Two bounded aggregate queries (all roles, all member ids) — constant
    # regardless of group size, not N+1. Cohorts are small; relationship
    # eager-loading would be premature here.
    resp.roles = await iam_service.get_group_roles(db, group_id)
    resp.member_ids = await iam_service.get_group_member_ids(db, group_id)
    return resp


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID = Depends(require_permission(Permissions.GROUPS_MANAGE)),
):
    await iam_service.delete_group(db, actor_id=actor, group_id=group_id)


@router.post("/groups/{group_id}/members", response_model=GroupMembersResponse)
async def add_group_member(
    group_id: uuid.UUID,
    body: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID = Depends(require_permission(Permissions.GROUPS_MANAGE)),
):
    members = await iam_service.add_member(db, actor_id=actor, group_id=group_id, user_id=body.user_id)
    return GroupMembersResponse(group_id=group_id, member_ids=members)


@router.delete("/groups/{group_id}/members/{user_id}", response_model=GroupMembersResponse)
async def remove_group_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID = Depends(require_permission(Permissions.GROUPS_MANAGE)),
):
    members = await iam_service.remove_member(db, actor_id=actor, group_id=group_id, user_id=user_id)
    return GroupMembersResponse(group_id=group_id, member_ids=members)


@router.post("/groups/{group_id}/roles", response_model=GroupRolesResponse)
async def add_group_role(
    group_id: uuid.UUID,
    body: GroupRoleRequest,
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID = Depends(require_permission(Permissions.GROUPS_MANAGE)),
):
    roles = await iam_service.add_group_role(db, actor_id=actor, group_id=group_id, role_name=body.role)
    return GroupRolesResponse(group_id=group_id, roles=roles)


@router.delete("/groups/{group_id}/roles/{role}", response_model=GroupRolesResponse)
async def remove_group_role(
    group_id: uuid.UUID,
    role: str,
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID = Depends(require_permission(Permissions.GROUPS_MANAGE)),
):
    roles = await iam_service.remove_group_role(db, actor_id=actor, group_id=group_id, role_name=role)
    return GroupRolesResponse(group_id=group_id, roles=roles)
