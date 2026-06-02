"""
Shared FastAPI dependencies.

`get_current_owner` is the forward-compat auth seam: every endpoint that
writes per-user data injects this dependency, and Phase 5 swaps the body
for real authentication (API key / JWT) without touching call sites.

Until then, every request is treated as owned by `settings.DEFAULT_OWNER_ID`
so existing data and new data share a single tenant.
"""
from __future__ import annotations

import uuid

from src.core.config import settings


async def get_current_owner() -> uuid.UUID:
    """Return the owning user/tenant UUID for the current request.

    Phase 0–4: always returns the single configured default owner.
    Phase 5: replaced with a real auth check (raises 401 on failure).
    """
    return uuid.UUID(settings.DEFAULT_OWNER_ID)
