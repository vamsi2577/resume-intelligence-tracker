"""
Pydantic schemas for Resume Generator API.

Extends the ChatGPT structured output format with:
  - job_title  (required) — exact role title from JD
  - job_description (optional) — full raw JD text
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


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

    # ── Resume sections ───────────────────────────────────
    summary: Optional[SummaryObject] = None
    skills: Optional[List[SkillCategory]] = None
    experience: Optional[List[ExperienceItem]] = None
    certifications: Optional[List[CertificationItem]] = None
    education: Optional[List[EducationItem]] = None


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
    job_description: str = Field(..., min_length=20)
    target_company: Optional[str] = Field(None, max_length=255)
    job_title: Optional[str] = Field(None, max_length=255)


class JDResumePreviewResponse(BaseModel):
    """Returned when `preview=true` — the tailored ResumeRequest, not a DOCX.

    Lets the client review/edit before committing to a download + auto-log.
    """
    tailored: ResumeRequest
