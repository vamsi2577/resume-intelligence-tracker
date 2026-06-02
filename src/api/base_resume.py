"""
API routes for the master / base résumé.

  GET  /api/v1/base-resume   — fetch current owner's résumé (404 if none)
  PUT  /api/v1/base-resume   — upsert (raw_text required, structured_json optional)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_owner
from src.db.session import get_db
from src.schemas.base_resume import BaseResumeResponse, BaseResumeUpsert
from src.services import base_resume_service

router = APIRouter(prefix="/api/v1", tags=["base-resume"])


@router.get("/base-resume", response_model=BaseResumeResponse)
async def get_base_resume(
    db: AsyncSession = Depends(get_db),
    owner_id: uuid.UUID = Depends(get_current_owner),
) -> BaseResumeResponse:
    row = await base_resume_service.get_required(db, owner_id)
    return BaseResumeResponse.model_validate(row)


@router.put("/base-resume", response_model=BaseResumeResponse)
async def put_base_resume(
    payload: BaseResumeUpsert,
    db: AsyncSession = Depends(get_db),
    owner_id: uuid.UUID = Depends(get_current_owner),
) -> BaseResumeResponse:
    row = await base_resume_service.upsert(db, owner_id, payload)
    return BaseResumeResponse.model_validate(row)
