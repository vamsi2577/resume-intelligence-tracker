"""
Pydantic schemas for the résumé-generation audit log.

Read-only — rows are written by the audit service, never by the client.
The history endpoint returns these for the dashboard "Generation history"
view.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ResumeGenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    correlation_id: Optional[str] = None
    status: str
    target_company: Optional[str] = None
    job_title: Optional[str] = None
    jd_chars: Optional[int] = None
    preview: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    duration_ms: Optional[int] = None
    application_id: Optional[uuid.UUID] = None
    error_message: Optional[str] = None
    # llm_raw_output is intentionally omitted from the list view (can be
    # large); fetch the single row if you need it.
    created_at: datetime


class GenerationStatsResponse(BaseModel):
    """Aggregate counters for the history header."""
    total: int = 0
    success: int = 0
    llm_error: int = 0
    validation_error: int = 0
    success_rate: float = 0.0
    avg_duration_ms: Optional[int] = None
    total_tokens: int = 0


class GenerationHistoryResponse(BaseModel):
    data: List[ResumeGenerationResponse]
    stats: GenerationStatsResponse
