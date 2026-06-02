"""
ORM models for Phase 2 Email Watcher.

Tables:
  - email_poll_state  — single-row timestamp tracker for Gmail polling
  - email_queue       — dedup store + failure queue for unprocessed emails
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class EmailPollState(Base):
    __tablename__ = "email_poll_state"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, default=1)
    last_poll_timestamp: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )

    def __repr__(self) -> str:
        return f"<EmailPollState last={self.last_poll_timestamp}>"


class EmailQueue(Base):
    __tablename__ = "email_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    classifier_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.Enum("pending", "processed", "unmatched", "failed", "ignored",
                name="email_queue_status"),
        nullable=False,
        default="pending",
    )
    retry_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_email_queue_status", "status"),
        Index("ix_email_queue_message_id", "message_id"),
    )

    def __repr__(self) -> str:
        return f"<EmailQueue {self.message_id} [{self.status}]>"
