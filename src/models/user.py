"""
ORM model for application users (tenants).

The `users` table is the root of all ownership: every data row
(job_applications, base_resumes, resume_generations) references a user via
`owner_id`. Introduced in Phase 1 of the multi-tenancy work.

Phase 1 still runs single-tenant — a single default user
(settings.DEFAULT_OWNER_ID) owns all existing data, seeded by migration 008.
Real sign-in / multiple users arrive in Phase 2 (auth).
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 320 = the maximum length of an email address (64 local + @ + 255 domain).
    # Uniqueness is enforced case-insensitively via a functional index on
    # lower(email) (see __table_args__), so "A@x.com" and "a@x.com" collide.
    email: Mapped[str] = mapped_column(String(320), nullable=False)

    # Soft-disable an account without deleting its data (hard-delete is Phase 5).
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default="true"
    )

    __table_args__ = (
        Index("ux_users_email", sa.text("lower(email)"), unique=True),
    )

    def __repr__(self) -> str:
        return f"<User {self.email} active={self.is_active}>"
