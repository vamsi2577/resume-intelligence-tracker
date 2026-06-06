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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.session import get_db
from src.models.user import User
from src.services import auth_service, iam_service, token_service
from src.utils.exceptions import UnauthorizedError


async def get_current_owner(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Return the owning user/tenant UUID for the current request.

    Resolution order:

    1. `Authorization: Bearer <token>` — a personal API token. Always honored
       when present (the client is explicitly authenticating), regardless of
       REQUIRE_AUTH; this is how the browser extension, which can't carry the
       HttpOnly cookie, talks to the RIT bridge. An invalid bearer token is a
       401 — never a silent fall-through to the default owner.
    2. REQUIRE_AUTH off (default): single configured default owner — no login
       required, non-breaking for the existing single-tenant deployment.
    3. REQUIRE_AUTH on: resolve the session cookie's JWT to a real user id,
       then confirm that user still exists and is active. Raise 401 when the
       cookie is missing/invalid or the account was deleted/deactivated — so an
       IAM deactivation takes effect on the next request instead of lingering
       until the JWT expires.
    """
    bearer = _extract_bearer(request)
    if bearer is not None:
        return await token_service.resolve_token(db, bearer)

    if not settings.REQUIRE_AUTH:
        return uuid.UUID(settings.DEFAULT_OWNER_ID)

    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise UnauthorizedError("Authentication required")

    claims = auth_service.decode_session(token)
    user = (
        await db.execute(select(User).where(User.id == claims.user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active or user.token_version != claims.token_version:
        # Unknown/deactivated user, or the session was revoked via
        # token_version bump ("log out everywhere").
        raise UnauthorizedError("Session is no longer valid")
    return claims.user_id


def _extract_bearer(request: Request) -> str | None:
    """Return the raw token from an `Authorization: Bearer <token>` header, or
    None when the header is absent. A malformed Authorization header (present
    but not a non-empty Bearer) is treated as a failed auth attempt → 401."""
    header = request.headers.get("Authorization")
    if header is None:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise UnauthorizedError("Malformed Authorization header")
    return value.strip()


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
