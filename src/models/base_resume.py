"""
ORM model for the user's master / base résumé.

The base résumé is the source the AI tailors against when a job
description comes in. One row per owner (see Phase 5: multi-tenant).
For now there is a single owner so this table is effectively a
singleton.
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.config import settings
from src.db.base import Base


def _default_owner_id() -> uuid.UUID:
    return uuid.UUID(settings.DEFAULT_OWNER_ID)


class BaseResume(Base):
    __tablename__ = "base_resumes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Phase 1: NOT NULL FK to users; UNIQUE keeps it one base résumé per user.
    # Defaults to the single tenant until Phase 2 supplies a real owner.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        default=_default_owner_id,
    )

    # Plain text version of the master résumé — what we feed into the
    # LLM prompt. Stored as TEXT so it tolerates very long résumés.
    raw_text: Mapped[str] = mapped_column(sa.Text, nullable=False)

    # Optional structured cache — when the user has already tuned the
    # résumé into ResumeRequest-shaped JSON, store it here so the AI
    # service can skip an extra normalisation step.
    structured_json: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)

    def __repr__(self) -> str:
        return f"<BaseResume owner={self.owner_id}>"
