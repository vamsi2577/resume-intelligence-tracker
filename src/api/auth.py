"""
Auth / identity routes (Phase 1b).

  GET /api/v1/auth/me — the caller's identity, roles, and effective permissions.

The dashboard's `<Can>` gate and admin nav read this to decide what UI to show.
The server still enforces every action via require_permission — /auth/me is a
convenience for the client, never the security boundary.

Login / registration / magic-link land in Phase 2. In Phase 1b the caller is
always the default owner.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_owner
from src.db.session import get_db
from src.schemas.iam import MeResponse
from src.services import iam_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/me", response_model=MeResponse)
async def me(
    db: AsyncSession = Depends(get_db),
    owner_id: uuid.UUID = Depends(get_current_owner),
) -> MeResponse:
    user = await iam_service.get_user(db, owner_id)  # raises 404 if missing
    roles = await iam_service.get_role_names(db, owner_id)
    permissions = await iam_service.get_effective_permissions(db, owner_id)
    return MeResponse(
        user_id=user.id,
        email=user.email,
        is_active=user.is_active,
        roles=roles,
        permissions=sorted(permissions),
    )
