"""
Authentication service (Phase 2 — magic-link sessions).

Flow:
  1. request_login(email) → mint a high-entropy token, store only its SHA-256
     hash with a short expiry, email a link containing the raw token.
  2. verify_login(email, raw_token) → validate (hash match, not expired, not
     consumed), mark consumed, get-or-create the user (auto-register, granted
     the default signup role), return the user.
  3. issue_session(user_id) / decode_session(jwt) → HS256 session JWT used as
     an HttpOnly cookie.

Only token HASHES are stored; raw tokens live only in the emailed link and the
session cookie. Tenancy is unchanged — a user's owner_id is their own user id.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.permissions import DEFAULT_SIGNUP_ROLE
from src.models.iam import Role, UserRole
from src.models.login_token import LoginToken
from src.models.user import User
from src.utils.exceptions import UnauthorizedError
from src.utils.logger import get_logger

logger = get_logger(__name__)

_JWT_ALG = "HS256"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


# ── Magic link ────────────────────────────────────────────

async def request_login(db: AsyncSession, email: str) -> str:
    """Create a login token for `email` and return the RAW token (the caller
    builds + sends the link). Only the hash is persisted."""
    email = _normalize_email(email)

    # Opportunistic hygiene: drop this email's stale tokens (already consumed,
    # or past expiry) so the table doesn't grow unbounded. Only dead rows are
    # removed — any still-valid outstanding link is left intact.
    now = _utcnow()
    await db.execute(
        delete(LoginToken).where(
            LoginToken.email == email,
            or_(LoginToken.consumed_at.is_not(None), LoginToken.expires_at <= now),
        )
    )

    raw = secrets.token_urlsafe(32)
    token = LoginToken(
        id=uuid.uuid4(),
        email=email,
        token_hash=_hash_token(raw),
        expires_at=now + timedelta(minutes=settings.MAGIC_LINK_TTL_MIN),
    )
    db.add(token)
    await db.flush()
    return raw


async def verify_login(db: AsyncSession, email: str, raw_token: str) -> User:
    """Validate and consume a login token; return the (created or existing)
    user. Raises UnauthorizedError on any failure (no detail on *why*, to
    avoid an oracle)."""
    email = _normalize_email(email)
    # Lock the token row (FOR UPDATE) so two concurrent verifies of the same
    # link can't both pass the single-use check: the second waits for the first
    # to commit consumed_at, then sees it set and is rejected below.
    row = (await db.execute(
        select(LoginToken)
        .where(LoginToken.token_hash == _hash_token(raw_token))
        .with_for_update()
    )).scalar_one_or_none()

    if (
        row is None
        or row.email != email
        or row.consumed_at is not None
        or row.expires_at <= _utcnow()
    ):
        raise UnauthorizedError("Invalid or expired login link")

    row.consumed_at = _utcnow()
    user = await _get_or_create_user(db, email)
    await db.flush()
    return user


async def _get_or_create_user(db: AsyncSession, email: str) -> User:
    existing = (await db.execute(
        select(User).where(User.email == email)
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    user = User(id=uuid.uuid4(), email=email, is_active=True)
    db.add(user)
    await db.flush()

    # Grant the default signup role (user).
    role = (await db.execute(
        select(Role).where(Role.name == DEFAULT_SIGNUP_ROLE)
    )).scalar_one_or_none()
    if role is not None:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    logger.info("User auto-registered via magic link", extra={"email": email})
    return user


# ── Session JWT ───────────────────────────────────────────

def issue_session(user_id: uuid.UUID) -> str:
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.SESSION_DAYS)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET.get_secret_value(), algorithm=_JWT_ALG)


def decode_session(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET.get_secret_value(), algorithms=[_JWT_ALG]
        )
        return uuid.UUID(payload["sub"])
    except Exception as e:  # jwt errors, bad uuid, missing sub
        raise UnauthorizedError("Invalid session") from e
