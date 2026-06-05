"""
Personal API token service (Phase 2 — bearer auth for non-browser clients).

  create_token(owner, name)  → mint a raw token, store only its SHA-256 hash,
                               return the (ApiToken, raw) pair. Raw is shown
                               to the user exactly once.
  resolve_token(raw)         → validate a bearer token (hash match, not revoked,
                               not expired, owner still active) and return the
                               owner id. Stamps last_used_at. Raises
                               UnauthorizedError on any failure.
  list_tokens / revoke_token → owner-scoped management for the UI.

Mirrors the magic-link token design (hash-at-rest, single source of truth in
Postgres) but these tokens are long-lived and explicitly user-managed.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.api_token import ApiToken
from src.models.user import User
from src.utils.exceptions import NotFoundError, UnauthorizedError
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Raw tokens are prefixed so they're recognizable in logs/UIs and so a leaked
# token can be string-matched by secret scanners.
TOKEN_PREFIX = "rit_"
# Length of the non-secret slug kept for display (prefix + first chars).
_DISPLAY_LEN = 12


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def create_token(
    db: AsyncSession,
    owner_id: uuid.UUID,
    name: str,
    expires_in_days: int | None = None,
) -> tuple[ApiToken, str]:
    """Mint a token for `owner_id`. Returns (row, raw_token); only the hash is
    persisted, so `raw_token` is the caller's one chance to read the secret."""
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    expires_at = (
        _utcnow() + timedelta(days=expires_in_days)
        if expires_in_days and expires_in_days > 0
        else None
    )
    token = ApiToken(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name=name.strip() or "API token",
        token_hash=_hash_token(raw),
        token_prefix=raw[:_DISPLAY_LEN],
        expires_at=expires_at,
    )
    db.add(token)
    await db.flush()
    logger.info("API token created", extra={"owner_id": str(owner_id), "token_id": str(token.id)})
    return token, raw


async def resolve_token(db: AsyncSession, raw: str) -> uuid.UUID:
    """Resolve a bearer token to its owner id, or raise UnauthorizedError.

    Validates: the hash exists, the token is not revoked, not expired, and the
    owning user still exists and is active. Updates last_used_at on success.

    Runs on every bearer-authenticated request, so the token and its owner are
    fetched in a single INNER JOIN (one round-trip). The inner join also means a
    token whose owner row is somehow gone simply doesn't match → 401.
    """
    now = _utcnow()
    result = (await db.execute(
        select(ApiToken, User)
        .join(User, User.id == ApiToken.owner_id)
        .where(ApiToken.token_hash == _hash_token(raw))
    )).first()

    if result is None:
        raise UnauthorizedError("Invalid or expired API token")
    token, user = result

    if (
        token.revoked_at is not None
        or (token.expires_at is not None and token.expires_at <= now)
        or not user.is_active
    ):
        raise UnauthorizedError("Invalid or expired API token")

    token.last_used_at = now
    # Flush the usage stamp now so the UPDATE is emitted within this request's
    # transaction (deterministic ordering, surfaces DB errors here rather than
    # later). Note: last_used_at is best-effort — it shares the request's
    # transaction, so a later rollback still discards it, which is fine for
    # "last seen" metadata.
    await db.flush()
    return token.owner_id


async def list_tokens(db: AsyncSession, owner_id: uuid.UUID) -> list[ApiToken]:
    return list((await db.execute(
        select(ApiToken)
        .where(ApiToken.owner_id == owner_id)
        .order_by(ApiToken.created_at.desc())
    )).scalars().all())


async def revoke_token(
    db: AsyncSession, owner_id: uuid.UUID, token_id: uuid.UUID
) -> ApiToken:
    """Revoke a token the caller owns. Raises NotFoundError (→ 404) when the
    token doesn't exist or belongs to another user (no existence leak)."""
    row = (await db.execute(
        select(ApiToken).where(
            ApiToken.id == token_id, ApiToken.owner_id == owner_id
        )
    )).scalar_one_or_none()
    if row is None:
        raise NotFoundError(resource="api_token", id=str(token_id))
    if row.revoked_at is None:
        row.revoked_at = _utcnow()
    await db.flush()
    return row
