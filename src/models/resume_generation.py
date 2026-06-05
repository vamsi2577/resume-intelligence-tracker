"""
ORM model for the résumé-generation audit log.

Every JD → résumé tailoring attempt writes one row here — success or
failure — so we can answer: how often does generation fail, why, how slow
is the model, how many tokens are we burning, and which application did a
given generation produce. Joins back to request logs via correlation_id.

Written from its OWN session (see generation_audit_service) so a failure
row survives even when the request session rolls back.
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.config import settings
from src.db.base import Base


def _default_owner_id() -> uuid.UUID:
    return uuid.UUID(settings.DEFAULT_OWNER_ID)

# Status vocabulary. Kept as a plain string column (not a PG enum) so new
# statuses don't require a migration — validated at the schema layer.
GENERATION_STATUSES = ("success", "llm_error", "validation_error")


class ResumeGeneration(Base):
    __tablename__ = "resume_generations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Phase 1: NOT NULL FK to users. The audit service already passes owner_id
    # on every write, so the default is just a safety net during transition.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        default=_default_owner_id,
    )

    # Join key back to structured request logs.
    correlation_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    # success | llm_error | validation_error
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False)

    # What the client asked for (hints) + JD size, for context.
    target_company: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    jd_chars: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    preview: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default="false"
    )

    # LLM call telemetry.
    provider: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    # Set on success once the application has been logged.
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Populated on failure only — error string + the raw model output so a
    # bad generation can be debugged without re-running it.
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    llm_raw_output: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.Index("ix_resume_generations_created_at", "created_at"),
        sa.Index("ix_resume_generations_status", "status"),
        sa.Index("ix_resume_generations_correlation_id", "correlation_id"),
        sa.Index("ix_resume_generations_application_id", "application_id"),
        # Owner-scoped history list + stats (Phase 1).
        sa.Index("ix_resume_generations_owner_created", "owner_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ResumeGeneration {self.status} {self.target_company} [{self.model}]>"
