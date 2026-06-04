"""
Pydantic schemas for Resume Generator API.

Extends the ChatGPT structured output format with:
  - job_title  (required) — exact role title from JD
  - job_description (optional) — full raw JD text
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

_WORK_TYPES = {"remote", "hybrid", "onsite"}


class JobMetadata(BaseModel):
    """Optional job-context fields the LLM can extract from the JD.

    Everything is optional and best-effort. The model is instructed to
    return null when a value is not explicitly stated in the JD, so we
    never fabricate a location or salary. These map onto the matching
    JobApplication columns when the application is auto-logged.
    """
    location: Optional[str] = Field(default=None, max_length=255)
    work_type: Optional[str] = Field(default=None)
    salary_range: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("work_type", mode="before")
    @classmethod
    def _normalize_work_type(cls, v):
        # Coerce to the WorkType enum vocabulary; drop anything unexpected
        # rather than failing the whole résumé generation.
        if not v:
            return None
        val = str(v).strip().lower()
        return val if val in _WORK_TYPES else None

    @field_validator("location", "salary_range", "notes", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class SummaryObject(BaseModel):
    summary_text: str
    summary_points: List[str] = []


class SkillCategory(BaseModel):
    category: str
    items: List[str]


class ExperienceItem(BaseModel):
    title: str
    company: str
    date: str
    bullets: List[str]
    tools: Optional[List[str]] = None


class CertificationItem(BaseModel):
    name: str


class EducationItem(BaseModel):
    degree: str
    university: str
    details: str


class ResumeRequest(BaseModel):
    # ── Job context (required for logging) ───────────────
    target_company: str = Field(..., min_length=1, max_length=255)
    job_title: str = Field(..., min_length=1, max_length=255)
    job_description: Optional[str] = None

    # ── Personal info (no hard-coded default; caller supplies, empty string allowed) ─────
    full_name: str = Field(default="", max_length=255)
    contact_info: str = Field(default="", max_length=512)

    @field_validator("full_name", "contact_info", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        # The LLM frequently emits explicit null for these when the base
        # résumé has no contact block; treat that as "use the default".
        return "" if v is None else v

    # ── Resume sections ───────────────────────────────────
    summary: Optional[SummaryObject] = None
    skills: Optional[List[SkillCategory]] = None
    experience: Optional[List[ExperienceItem]] = None
    certifications: Optional[List[CertificationItem]] = None
    education: Optional[List[EducationItem]] = None

    # ── JD-extracted job context (auto-fills the tracker row) ─────────
    # Not rendered into the DOCX; written onto the JobApplication on log.
    job_metadata: Optional[JobMetadata] = None


class ResumeGenerateResponse(BaseModel):
    """Returned in headers/metadata — DOCX is streamed directly."""
    application_id: str
    company_name: str
    job_title: str
    duplicate_warning: bool = False
    filename: str


class JDResumeRequest(BaseModel):
    """Body for POST /api/v1/generate-resume-from-jd.

    The backend tailors the stored base résumé to this JD using the LLM
    provider configured in src/core/config.py.
    """
    # Upper bound guards against multi-MB pastes inflating LLM token cost
    # and DB storage. ~20k chars comfortably fits the longest real JDs.
    job_description: str = Field(..., min_length=20, max_length=20_000)
    target_company: Optional[str] = Field(None, max_length=255)
    job_title: Optional[str] = Field(None, max_length=255)


class JDResumePreviewResponse(BaseModel):
    """Returned when `preview=true` — the tailored ResumeRequest, not a DOCX.

    Lets the client review/edit before committing to a download + auto-log.
    """
    tailored: ResumeRequest
