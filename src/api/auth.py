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

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_owner
from src.core.config import settings
from src.db.session import get_db
from src.schemas.auth import RequestLinkRequest, RequestLinkResponse, VerifyResponse
from src.schemas.iam import MeResponse
from src.services import auth_service, iam_service
from src.utils.email import send_email

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _set_session_cookie(response: Response, user_id: uuid.UUID) -> None:
    token = auth_service.issue_session(user_id)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.APP_ENV == "production",
        path="/",
    )


@router.post("/request-link", response_model=RequestLinkResponse)
async def request_link(
    body: RequestLinkRequest,
    db: AsyncSession = Depends(get_db),
) -> RequestLinkResponse:
    """Email a magic sign-in link. Always returns the same generic response so
    it never reveals whether the address has an account."""
    raw = await auth_service.request_login(db, body.email)
    link = f"{settings.APP_BASE_URL}/login/verify?token={raw}&email={body.email}"
    send_email(
        to=body.email,
        subject="Your Resume Intelligence sign-in link",
        body=f"Click to sign in (valid {settings.MAGIC_LINK_TTL_MIN} min):\n\n{link}\n",
    )
    return RequestLinkResponse()


@router.get("/verify", response_model=VerifyResponse)
async def verify(
    response: Response,
    token: str = Query(..., min_length=10),
    email: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> VerifyResponse:
    """Consume a magic-link token, (auto-)create the user, and set the session
    cookie. Raises 401 on an invalid/expired/used link."""
    user = await auth_service.verify_login(db, email, token)
    _set_session_cookie(response, user.id)
    return VerifyResponse(user_id=user.id, email=user.email)


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


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
