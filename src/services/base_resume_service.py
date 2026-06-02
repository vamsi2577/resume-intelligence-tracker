"""
Service layer for the master / base résumé.

Single-row-per-owner: GET returns the current row (or None), PUT upserts.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base_resume import BaseResume
from src.schemas.base_resume import BaseResumeUpsert
from src.utils.exceptions import NotFoundError
from src.utils.logger import get_logger
from src.utils.metrics import track_db_query

logger = get_logger(__name__)


@track_db_query("get_base_resume")
async def get_for_owner(db: AsyncSession, owner_id: uuid.UUID) -> BaseResume | None:
    stmt = select(BaseResume).where(BaseResume.owner_id == owner_id)
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_required(db: AsyncSession, owner_id: uuid.UUID) -> BaseResume:
    row = await get_for_owner(db, owner_id)
    if row is None:
        raise NotFoundError("base_resume", str(owner_id))
    return row


@track_db_query("upsert_base_resume")
async def upsert(
    db: AsyncSession, owner_id: uuid.UUID, payload: BaseResumeUpsert
) -> BaseResume:
    existing = await get_for_owner(db, owner_id)
    if existing is None:
        row = BaseResume(
            id=uuid.uuid4(),
            owner_id=owner_id,
            raw_text=payload.raw_text,
            structured_json=payload.structured_json,
        )
        db.add(row)
        logger.info("Base résumé created", extra={"owner_id": str(owner_id)})
    else:
        existing.raw_text = payload.raw_text
        existing.structured_json = payload.structured_json
        row = existing
        logger.info("Base résumé updated", extra={"owner_id": str(owner_id)})
    await db.flush()
    return row
