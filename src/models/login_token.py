"""
ORM model for magic-link login tokens (Phase 2 auth).

A short-lived, single-use token issued by POST /auth/request-link and
consumed by GET /auth/verify. Only the SHA-256 hash of the token is stored —
the raw token lives only in the emailed link.

A DB table (not Redis) on purpose: avoids new infra at this stage; the table
is tiny and self-expiring (rows are consumed or aged out).
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class LoginToken(Base):
    __tablename__ = "login_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # SHA-256 hex digest of the raw token (64 chars). Unique so a lookup by
    # hash is a single indexed probe.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    # Set when the token is redeemed — enforces single use.
    consumed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_login_tokens_email", "email"),
    )

    def __repr__(self) -> str:
        return f"<LoginToken {self.email} exp={self.expires_at}>"
