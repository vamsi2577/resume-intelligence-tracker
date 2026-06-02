"""
Pydantic schemas for Phase 2 Email Watcher.

Schemas:
  - EmailEventRequest   — POST /applications/{id}/email-event (from n8n)
  - EmailQueueResponse  — single email_queue record
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EmailCategory(str, Enum):
    application_received = "application_received"
    screening = "screening"
    interview_scheduled = "interview_scheduled"
    assessment_request = "assessment_request"
    rejection = "rejection"
    offer = "offer"
    recruiter_outreach = "recruiter_outreach"
    ignore = "ignore"


class EmailQueueStatus(str, Enum):
    pending = "pending"
    processed = "processed"
    unmatched = "unmatched"
    failed = "failed"
    ignored = "ignored"


# ── Classifier output contract (from Gemini) ──────────────

class ClassifierOutput(BaseModel):
    category: EmailCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    company: str | None = None
    role: str | None = None
    interview_date: str | None = None   # YYYY-MM-DD or null
    key_phrases: list[str] = Field(default_factory=list)


# ── API request from n8n ──────────────────────────────────

class EmailEventRequest(BaseModel):
    model_config = {"extra": "forbid"}

    message_id: str = Field(..., max_length=255)
    subject: str | None = None
    sender: str | None = None
    raw_body: str | None = None
    classifier_output: ClassifierOutput


# ── Response schemas ──────────────────────────────────────

class EmailQueueResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    message_id: str
    subject: str | None
    sender: str | None
    classifier_output: dict[str, Any] | None
    status: EmailQueueStatus
    retry_count: int
    error: str | None
    created_at: datetime
    updated_at: datetime
