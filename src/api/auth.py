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

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_owner
from src.core.config import settings
from src.db.session import get_db
from src.schemas.api_token import (
    CreateTokenRequest,
    CreateTokenResponse,
    TokenInfo,
)
from src.schemas.auth import RequestLinkRequest, RequestLinkResponse, VerifyResponse
from src.schemas.iam import MeResponse
from src.services import auth_service, iam_service, token_service
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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> RequestLinkResponse:
    """Email a magic sign-in link. Always returns the same generic response so
    it never reveals whether the address has an account.

    The actual send is queued as a background task so the synchronous SMTP
    handshake never blocks the event loop (and never affects response timing,
    which would otherwise leak account existence)."""
    raw = await auth_service.request_login(db, body.email)
    link = f"{settings.APP_BASE_URL}/login/verify?token={raw}&email={body.email}"
    background_tasks.add_task(
        send_email,
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


# ── Personal API tokens ───────────────────────────────────
# Bearer credentials a user mints for clients that can't carry the session
# cookie (chiefly the H1B Scout extension). Management is scoped to the caller
# via get_current_owner — you can only see and revoke your own tokens.

@router.post(
    "/tokens",
    response_model=CreateTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_token(
    body: CreateTokenRequest,
    db: AsyncSession = Depends(get_db),
    owner_id: uuid.UUID = Depends(get_current_owner),
) -> CreateTokenResponse:
    """Mint a personal API token. The raw secret is returned exactly once —
    it is hashed at rest and can never be retrieved again."""
    token, raw = await token_service.create_token(
        db, owner_id, body.name, body.expires_in_days
    )
    return CreateTokenResponse(token=raw, **TokenInfo.model_validate(token).model_dump())


@router.get("/tokens", response_model=list[TokenInfo])
async def list_tokens(
    db: AsyncSession = Depends(get_db),
    owner_id: uuid.UUID = Depends(get_current_owner),
) -> list[TokenInfo]:
    rows = await token_service.list_tokens(db, owner_id)
    return [TokenInfo.model_validate(r) for r in rows]


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    owner_id: uuid.UUID = Depends(get_current_owner),
) -> Response:
    """Revoke one of the caller's tokens. 404 if it doesn't exist or belongs to
    someone else."""
    await token_service.revoke_token(db, owner_id, token_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
