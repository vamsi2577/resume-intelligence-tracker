"""
Pydantic schemas for job application API.

Schemas:
  - ApplicationCreateRequest  — POST /log-application
  - ApplicationUpdateRequest  — PATCH /log-application/{id}
  - ApplicationResponse       — single application returned to client
  - ApplicationListResponse   — paginated list
  - StatusHistoryResponse     — single history entry
  - PaginationMeta            — reusable pagination envelope
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ── Enums ─────────────────────────────────────────────────

class ApplicationStatus(str, Enum):
    applied = "applied"
    screening = "screening"
    interview = "interview"
    assessment = "assessment"
    offer = "offer"
    rejected = "rejected"
    ghosted = "ghosted"
    withdrawn = "withdrawn"


class ApplicationSource(str, Enum):
    manual = "manual"
    resume_generator = "resume_generator"


class WorkType(str, Enum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"


# ── Shared validator helpers ───────────────────────────────

def _validate_not_future(value: date | None, field_name: str) -> date | None:
    if value is not None and value > date.today():
        raise ValueError(f"{field_name} cannot be in the future")
    return value


def _validate_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("job_url must be a valid http/https URL")
    return value


# ── Request schemas ────────────────────────────────────────

class ApplicationCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    # Mandatory
    company_name: str = Field(..., min_length=1, max_length=255)
    job_title: str = Field(..., min_length=1, max_length=255)
    source: ApplicationSource
    applied_date: date

    # Optional
    status: ApplicationStatus = ApplicationStatus.applied
    job_url: str | None = None
    job_id: str | None = Field(default=None, max_length=100)
    job_description: str | None = None
    resume_version: str | None = Field(default=None, max_length=50)
    resume_content: dict | None = None
    notes: str | None = None
    salary_range: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    work_type: WorkType | None = None
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None
    follow_up_date: date | None = None
    needs_review: bool = False

    @field_validator("applied_date")
    @classmethod
    def applied_date_not_future(cls, v: date) -> date:
        return _validate_not_future(v, "applied_date")

    @field_validator("job_url")
    @classmethod
    def validate_job_url(cls, v: str | None) -> str | None:
        return _validate_url(v)


class ApplicationUpdateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    # All fields optional for PATCH
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    job_title: str | None = Field(default=None, min_length=1, max_length=255)
    source: ApplicationSource | None = None
    status: ApplicationStatus | None = None
    applied_date: date | None = None
    job_url: str | None = None
    job_id: str | None = Field(default=None, max_length=100)
    job_description: str | None = None
    resume_version: str | None = Field(default=None, max_length=50)
    resume_content: dict | None = None
    notes: str | None = None
    salary_range: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    work_type: WorkType | None = None
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None
    follow_up_date: date | None = None
    needs_review: bool | None = None

    @field_validator("applied_date")
    @classmethod
    def applied_date_not_future(cls, v: date | None) -> date | None:
        return _validate_not_future(v, "applied_date")

    @field_validator("job_url")
    @classmethod
    def validate_job_url(cls, v: str | None) -> str | None:
        return _validate_url(v)

    @model_validator(mode="before")
    @classmethod
    def at_least_one_field_required(cls, values: Any) -> Any:
        if isinstance(values, dict):
            provided = {k: v for k, v in values.items() if v is not None}
            if not provided:
                raise ValueError("PATCH request must include at least one non-null field")
        return values


# ── Response schemas ───────────────────────────────────────

class StatusHistoryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    application_id: uuid.UUID
    status: ApplicationStatus
    changed_at: datetime
    note: str | None
    created_at: datetime


class ApplicationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    company_name: str
    job_title: str
    source: ApplicationSource
    status: ApplicationStatus
    applied_date: date
    job_url: str | None
    job_id: str | None
    job_description: str | None
    resume_version: str | None
    resume_content: dict | None
    notes: str | None
    salary_range: str | None
    location: str | None
    address: str | None
    work_type: WorkType | None
    contact_name: str | None
    contact_email: str | None
    follow_up_date: date | None
    needs_review: bool
    created_at: datetime
    updated_at: datetime
    duplicate_warning: bool = False


class PaginationMeta(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int


class ApplicationListResponse(BaseModel):
    data: list[ApplicationResponse]
    pagination: PaginationMeta
    meta: dict[str, Any] = {}


class WeeklyTrendPoint(BaseModel):
    week: date
    count: int


class SourceBreakdown(BaseModel):
    manual: int
    resume_generator: int


class StatsResponse(BaseModel):
    total: int
    interview: int
    rejected: int
    offer: int
    needs_review: int
    ats_pass_rate: float
    source_breakdown: SourceBreakdown
    weekly_trend: list[WeeklyTrendPoint]


# ── Filter / query contract ───────────────────────────────────

class SortField(str, Enum):
    applied_date = "applied_date"
    updated_at = "updated_at"
    company_name = "company_name"
    status = "status"
    job_title = "job_title"


class SortDir(str, Enum):
    asc = "asc"
    desc = "desc"


class ApplicationFilters(BaseModel):
    """Typed query contract passed from route → service."""
    company: list[str] = Field(default_factory=list)
    status: list[ApplicationStatus] = Field(default_factory=list)
    source: ApplicationSource | None = None
    work_type: WorkType | None = None
    search: str | None = None           # ILIKE on company_name OR job_title
    job_title: str | None = None          # partial match
    date_from: date | None = None
    date_to: date | None = None
    needs_review: bool | None = None
    include_deleted: bool = False        # if false, hides soft-deleted rows
    ids: list[uuid.UUID] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    sort_by: SortField = SortField.applied_date
    sort_dir: SortDir = SortDir.desc

    @model_validator(mode="after")
    def date_range_valid(self) -> "ApplicationFilters":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from cannot be after date_to")
        return self
