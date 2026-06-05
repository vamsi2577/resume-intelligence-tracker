"""
Read-only API for the résumé-generation audit log.

  GET /api/v1/generation-history  — recent generation attempts + aggregate
                                    stats for the dashboard observability view.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_owner
from src.db.session import get_db
from src.schemas.resume_generation import (
    GenerationHistoryResponse,
    ResumeGenerationResponse,
)
from src.services import generation_audit_service

router = APIRouter(prefix="/api/v1", tags=["observability"])


@router.get("/generation-history", response_model=GenerationHistoryResponse)
async def generation_history(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    owner_id: uuid.UUID = Depends(get_current_owner),
) -> GenerationHistoryResponse:
    rows = await generation_audit_service.list_recent(db, owner_id, limit=limit)
    stats = await generation_audit_service.get_stats(db, owner_id)
    return GenerationHistoryResponse(
        data=[ResumeGenerationResponse.model_validate(r) for r in rows],
        stats=stats,
    )
