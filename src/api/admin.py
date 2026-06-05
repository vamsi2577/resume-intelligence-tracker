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
    AdminUserDetailResponse,
    AdminUserResponse,
    AssignRoleRequest,
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
