"""
ORM models for job applications and status history.

Tables:
  - job_applications
  - application_status_history
"""
import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import Date, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

# ── Enums ─────────────────────────────────────────────────

ApplicationStatusEnum = Enum(
    "applied",
    "screening",
    "interview",
    "assessment",
    "offer",
    "rejected",
    "ghosted",
    "withdrawn",
    name="application_status",
)

ApplicationSourceEnum = Enum(
    "manual",
    "resume_generator",
    name="application_source",
)

WorkTypeEnum = Enum(
    "remote",
    "hybrid",
    "onsite",
    name="work_type",
)


# ── Models ────────────────────────────────────────────────

class JobApplication(Base):
    __tablename__ = "job_applications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Mandatory fields ──────────────────────────────────
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(ApplicationSourceEnum, nullable=False)
    status: Mapped[str] = mapped_column(
        ApplicationStatusEnum, nullable=False, default="applied"
    )
    applied_date: Mapped[date] = mapped_column(Date, nullable=False)

    # ── Optional fields ───────────────────────────────────
    job_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resume_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_type: Mapped[str | None] = mapped_column(WorkTypeEnum, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ── Relationship ──────────────────────────────────────
    status_history: Mapped[list["ApplicationStatusHistory"]] = relationship(
        "ApplicationStatusHistory",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationStatusHistory.changed_at",
    )

    # ── Indexes ───────────────────────────────────────────
    __table_args__ = (
        Index("ix_job_applications_company_name", "company_name"),
        Index("ix_job_applications_status", "status"),
        Index("ix_job_applications_applied_date", "applied_date"),
        Index("ix_job_applications_company_job_id", "company_name", "job_id"),
    )

    def __repr__(self) -> str:
        return f"<JobApplication {self.company_name} — {self.job_title} [{self.status}]>"


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(ApplicationStatusEnum, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationship ──────────────────────────────────────
    application: Mapped["JobApplication"] = relationship(
        "JobApplication", back_populates="status_history"
    )

    __table_args__ = (
        Index("ix_status_history_application_id", "application_id"),
    )

    def __repr__(self) -> str:
        return f"<StatusHistory app={self.application_id} status={self.status}>"
