"""
Pydantic schemas for the IAM / auth surface (Phase 1b).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class MeResponse(BaseModel):
    """GET /api/v1/auth/me — the caller's identity + effective access."""
    user_id: uuid.UUID
    email: str
    is_active: bool
    roles: List[str]
    permissions: List[str]
    # Populated in Phase 4 (subscription entitlements); empty until then.
    plan_entitlements: List[str] = []


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime


class AdminUserDetailResponse(AdminUserResponse):
    roles: List[str] = []


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    is_system: bool


class AssignRoleRequest(BaseModel):
    role: str = Field(..., min_length=1, max_length=64)


class RolesResponse(BaseModel):
    """Returned after assign/revoke — the user's resulting role set."""
    user_id: uuid.UUID
    roles: List[str]


# ── Groups ────────────────────────────────────────────────

class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None


class GroupDetailResponse(GroupResponse):
    roles: List[str] = []
    member_ids: List[uuid.UUID] = []


class CreateGroupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID


class GroupRoleRequest(BaseModel):
    role: str = Field(..., min_length=1, max_length=64)


class GroupMembersResponse(BaseModel):
    group_id: uuid.UUID
    member_ids: List[uuid.UUID]


class GroupRolesResponse(BaseModel):
    group_id: uuid.UUID
    roles: List[str]
