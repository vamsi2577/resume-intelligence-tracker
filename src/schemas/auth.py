"""
Pydantic schemas for the magic-link auth flow (Phase 2).
"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr


class RequestLinkRequest(BaseModel):
    email: EmailStr


class RequestLinkResponse(BaseModel):
    # Deliberately generic — never reveals whether the email exists.
    ok: bool = True
    message: str = "If that email is valid, a sign-in link has been sent."


class VerifyResponse(BaseModel):
    user_id: uuid.UUID
    email: str
