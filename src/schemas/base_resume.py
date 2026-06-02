"""
Pydantic schemas for the base / master résumé endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class BaseResumeUpsert(BaseModel):
    """Body for PUT /api/v1/base-resume."""

    raw_text: str = Field(..., min_length=1)
    structured_json: dict[str, Any] | None = None


class BaseResumeResponse(BaseModel):
    id: UUID
    owner_id: UUID | None
    raw_text: str
    structured_json: dict[str, Any] | None
    updated_at: datetime

    model_config = {"from_attributes": True}
