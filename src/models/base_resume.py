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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class BaseResume(Base):
    __tablename__ = "base_resumes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Nullable now — populated with settings.DEFAULT_OWNER_ID via the
    # auth seam. Phase 5 will make it non-null with a real FK.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, unique=True
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
