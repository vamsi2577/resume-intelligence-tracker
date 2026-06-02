"""
Email watcher service layer.

Handles:
  - Processing incoming email events from n8n
  - Matching emails to existing applications (fuzzy company name)
  - Auto-creating unmatched applications with needs_review=True
  - Updating application status based on classifier output
  - Writing to email_queue for dedup + audit trail
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.application import JobApplication, ApplicationStatusHistory
from src.models.email_watcher import EmailQueue
from src.schemas.application import ApplicationStatus
from src.schemas.email_watcher import (
    ClassifierOutput,
    EmailCategory,
    EmailEventRequest,
    EmailQueueResponse,
)
from src.utils.exceptions import DuplicateError
from src.utils.logger import get_logger
from src.utils.metrics import track_db_query

logger = get_logger(__name__)

# Maps classifier category → DB ApplicationStatus
CATEGORY_TO_STATUS: dict[str, str] = {
    EmailCategory.application_received: ApplicationStatus.applied,
    EmailCategory.screening:            ApplicationStatus.screening,
    EmailCategory.interview_scheduled:  ApplicationStatus.interview,
    EmailCategory.assessment_request:   ApplicationStatus.assessment,
    EmailCategory.rejection:            ApplicationStatus.rejected,
    EmailCategory.offer:                ApplicationStatus.offer,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _find_matching_application(
    db: AsyncSession, company: str
) -> JobApplication | None:
    """Case-insensitive exact match on company_name."""
    stmt = select(JobApplication).where(
        func.lower(JobApplication.company_name) == company.lower()
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def _is_duplicate_message(db: AsyncSession, message_id: str) -> bool:
    stmt = select(EmailQueue).where(EmailQueue.message_id == message_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _write_queue(
    db: AsyncSession,
    request: EmailEventRequest,
    status: str,
    error: str | None = None,
) -> EmailQueue:
    entry = EmailQueue(
        id=uuid.uuid4(),
        message_id=request.message_id,
        subject=request.subject,
        sender=request.sender,
        raw_body=request.raw_body,
        classifier_output=request.classifier_output.model_dump(),
        status=status,
        error=error,
    )
    db.add(entry)
    await db.flush()
    return entry


@track_db_query("process_email_event")
async def process_email_event(
    db: AsyncSession,
    request: EmailEventRequest,
) -> dict:
    """
    Main entry point called by POST /applications/email-event.

    Returns a dict with: status, action, application_id (if matched/created)
    """
    clf: ClassifierOutput = request.classifier_output
    category = clf.category

    # ── Dedup check ───────────────────────────────────────
    if await _is_duplicate_message(db, request.message_id):
        logger.info("Duplicate email skipped", extra={"message_id": request.message_id})
        return {"status": "skipped", "reason": "duplicate"}

    # ── Skip ignored categories ───────────────────────────
    if category in (EmailCategory.ignore, EmailCategory.recruiter_outreach):
        await _write_queue(db, request, "ignored")
        logger.info("Email ignored", extra={"category": category, "message_id": request.message_id})
        return {"status": "ignored", "category": category}

    # ── No company extracted → queue as unmatched ─────────
    if not clf.company:
        await _write_queue(db, request, "unmatched", error="No company extracted")
        return {"status": "unmatched", "reason": "no_company"}

    # ── Try to match existing application ─────────────────
    app = await _find_matching_application(db, clf.company)
    new_status = CATEGORY_TO_STATUS.get(category)

    if app:
        # Update status if mapping exists and status actually changed
        if new_status and new_status.value != app.status:
            old_status = app.status
            app.status = new_status.value
            app.updated_at = _utcnow()
            db.add(ApplicationStatusHistory(
                id=uuid.uuid4(),
                application_id=app.id,
                status=new_status.value,
                changed_at=_utcnow(),
                note=f"Auto-updated via email: {', '.join(clf.key_phrases)}",
            ))
            logger.info(
                "Application status updated via email",
                extra={
                    "application_id": str(app.id),
                    "company": clf.company,
                    "old_status": old_status,
                    "new_status": new_status.value,
                },
            )
        await _write_queue(db, request, "processed")
        return {"status": "processed", "action": "updated", "application_id": str(app.id)}

    # ── No match → auto-create with needs_review=True ─────
    new_app = JobApplication(
        id=uuid.uuid4(),
        company_name=clf.company,
        job_title=clf.role or "Unknown Role",
        source="resume_generator",
        status=new_status.value if new_status else ApplicationStatus.applied.value,
        applied_date=_utcnow().date(),
        needs_review=True,
    )
    db.add(new_app)
    db.add(ApplicationStatusHistory(
        id=uuid.uuid4(),
        application_id=new_app.id,
        status=new_app.status,
        changed_at=_utcnow(),
        note="Auto-created from email classifier",
    ))
    await db.flush()
    await _write_queue(db, request, "unmatched")

    logger.info(
        "Application auto-created from email",
        extra={"application_id": str(new_app.id), "company": clf.company, "needs_review": True},
    )
    return {
        "status": "unmatched",
        "action": "auto_created",
        "application_id": str(new_app.id),
    }
