"""
API routes for Phase 2 Email Watcher.

Endpoints:
  POST /api/v1/applications/email-event  — called by n8n after classification
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.email_watcher import EmailEventRequest
from src.services import email_watcher_service
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["email-watcher"])


@router.post(
    "/applications/email-event",
    status_code=status.HTTP_200_OK,
)
async def receive_email_event(
    body: EmailEventRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await email_watcher_service.process_email_event(db, body)
    logger.info("Email event processed", extra={"result": result})
    return result
