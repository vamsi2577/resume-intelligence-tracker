"""
ORM model for auth audit events (Phase 5 auth-hardening).

A security-forensics trail for the authentication surface: link requests, verify
success/failure, "log out everywhere", and API-token mint/revoke. Distinct from
IamAuditLog (which tracks role/group changes) because the shape differs — auth
events may have no user (a failed/unknown verify) and carry the client IP.

Best-effort: writes share the request and never block the user flow.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class AuthEvent(Base):
    __tablename__ = "auth_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # e.g. "login.request", "login.verify.success", "login.verify.fail",
    # "logout.all", "token.create", "token.revoke".
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Null when the event has no resolved/known user (e.g. a failed verify).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_auth_events_type_created", "event_type", "created_at"),
        Index("ix_auth_events_user", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<AuthEvent {self.event_type} user={self.user_id}>"
