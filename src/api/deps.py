"""
Shared FastAPI dependencies.

`get_current_owner` is the forward-compat auth seam: every endpoint that
writes per-user data injects this dependency, and Phase 5 swaps the body
for real authentication (API key / JWT) without touching call sites.

Until then, every request is treated as owned by `settings.DEFAULT_OWNER_ID`
so existing data and new data share a single tenant.
"""
from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.session import get_db
from src.services import auth_service, iam_service
from src.utils.exceptions import UnauthorizedError


async def get_current_owner(request: Request) -> uuid.UUID:
    """Return the owning user/tenant UUID for the current request.

    - REQUIRE_AUTH off (default): single configured default owner — no login
      required, non-breaking.
    - REQUIRE_AUTH on: resolve the session cookie's JWT to a real user id;
      raise 401 (UnauthorizedError) when the cookie is missing or invalid.
    """
    if not settings.REQUIRE_AUTH:
        return uuid.UUID(settings.DEFAULT_OWNER_ID)

    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise UnauthorizedError("Authentication required")
    return auth_service.decode_session(token)


def require_permission(permission: str) -> Callable:
    """Dependency factory: require the current user to hold `permission`.

    Authorization (this check) is orthogonal to tenancy (owner_id). Resolves
    the caller's effective permissions (direct roles + roles via group
    membership) and raises 403 if `permission` is absent. Returns the
    caller's id so routes can still use it.

    In Phase 1b the caller is always the default owner (user + superadmin), so
    every check passes — this becomes meaningful once real users sign in
    (Phase 2).
    """

    async def _checker(
        owner_id: uuid.UUID = Depends(get_current_owner),
        db: AsyncSession = Depends(get_db),
    ) -> uuid.UUID:
        perms = await iam_service.get_effective_permissions(db, owner_id)
        if permission not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )
        return owner_id

    return _checker
