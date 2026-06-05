"""
Pydantic schemas for personal API tokens (Phase 2).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateTokenRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    # Optional lifetime; omit / null for a non-expiring token.
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class TokenInfo(BaseModel):
    """A token as shown in listings — never includes the secret."""
    id: uuid.UUID
    name: str
    token_prefix: str
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateTokenResponse(TokenInfo):
    """Returned once at creation — carries the raw secret. Store it now; it is
    never retrievable again."""
    token: str
