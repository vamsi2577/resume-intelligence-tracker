"""
ORM model for personal API tokens (Phase 2 — non-browser auth).

A long-lived bearer credential a user mints for clients that can't carry the
HttpOnly session cookie — chiefly the H1B Scout browser extension, whose
`chrome-extension://` origin cannot send the cookie. The user pastes the raw
token into the extension once; the extension then calls the RIT-bridge
endpoints with `Authorization: Bearer <token>`.

Only the SHA-256 hash of the token is stored; the raw value is shown to the
user exactly once at creation. `token_prefix` keeps a short, non-secret slug
(e.g. "rit_a1b2c3d4") so the UI can label tokens in a list without revealing
the secret.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # The owning user. CASCADE so deleting a user removes their tokens.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Human label so the user can tell tokens apart ("Work laptop extension").
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # SHA-256 hex digest of the raw token (64 chars). Unique → lookup by hash
    # is a single indexed probe.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Short non-secret prefix shown in listings (e.g. "rit_a1b2c3d4").
    token_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    # Optional expiry; NULL = never expires.
    expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    # Set when the user revokes the token — a revoked token is permanently dead.
    revoked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    # Best-effort "last seen" for the management UI; updated on use.
    last_used_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_api_tokens_owner_id", "owner_id"),
    )

    def __repr__(self) -> str:
        return f"<ApiToken {self.token_prefix} owner={self.owner_id}>"
