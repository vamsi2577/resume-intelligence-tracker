"""
Resume Generator service layer.

Handles:
  - DOCX generation via docx_builder
  - Auto-logging the application to job_applications
  - Storing resume_content (JSONB) and job_description
  - Soft duplicate detection (same company + job_title + today)
"""
from __future__ import annotations

import io
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.application import ApplicationStatusHistory, JobApplication
from src.schemas.application import ApplicationSource, ApplicationStatus
from src.schemas.resume_generator import ResumeGenerateResponse, ResumeRequest
from src.utils.docx_builder import build_docx, build_filename
from src.utils.exceptions import DuplicateError
from src.utils.logger import get_logger
from src.utils.metrics import track_db_query

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _find_existing(
    db: AsyncSession,
    owner_id: uuid.UUID,
    company_name: str,
    job_title: str,
    applied_date: date,
) -> JobApplication | None:
    """Soft duplicate check: same owner + company + job_title + date."""
    stmt = select(JobApplication).where(
        JobApplication.owner_id == owner_id,
        func.lower(JobApplication.company_name) == company_name.lower(),
        func.lower(JobApplication.job_title) == job_title.lower(),
        JobApplication.applied_date == applied_date,
    )
    result = await db.execute(stmt)
    return result.scalars().first()


@track_db_query("generate_and_log_resume")
async def generate_and_log(
    db: AsyncSession,
    request: ResumeRequest,
    owner_id: uuid.UUID,
) -> tuple[io.BytesIO, str, ResumeGenerateResponse]:
    """
    Generates DOCX and logs the application.

    Returns:
        (docx_stream, filename, metadata_response)
    """
    today = date.today()
    duplicate_warning = False

    # ── Soft duplicate check ──────────────────────────────
    existing = await _find_existing(db, owner_id, request.target_company, request.job_title, today)
    if existing:
        duplicate_warning = True
        logger.info(
            "Soft duplicate detected for resume generation",
            extra={
                "application_id": str(existing.id),
                "company": request.target_company,
                "job_title": request.job_title,
            },
        )

    # ── JD-extracted job context (auto-fill optional tracker fields) ──
    meta = request.job_metadata

    # ── Log application ───────────────────────────────────
    app_id = uuid.uuid4()
    app = JobApplication(
        id=app_id,
        owner_id=owner_id,
        company_name=request.target_company,
        job_title=request.job_title,
        source=ApplicationSource.resume_generator.value,
        status=ApplicationStatus.applied.value,
        applied_date=today,
        job_description=request.job_description,
        resume_content=request.model_dump(exclude={"job_description", "job_metadata"}),
        location=(meta.location if meta else None),
        work_type=(meta.work_type if meta else None),
        salary_range=(meta.salary_range if meta else None),
        notes=(meta.notes if meta else None),
        needs_review=False,
    )
    db.add(app)
    db.add(ApplicationStatusHistory(
        id=uuid.uuid4(),
        application_id=app_id,
        status=ApplicationStatus.applied.value,
        changed_at=_utcnow(),
        note="Auto-logged via resume generator",
    ))
    await db.flush()

    logger.info(
        "Application logged via resume generator",
        extra={
            "application_id": str(app_id),
            "company": request.target_company,
            "job_title": request.job_title,
            "duplicate_warning": duplicate_warning,
            "autofilled_fields": [
                k for k in ("location", "work_type", "salary_range", "notes")
                if meta and getattr(meta, k)
            ] if meta else [],
        },
    )

    # ── Generate DOCX ─────────────────────────────────────
    docx_stream = build_docx(request)
    filename = build_filename(request)

    metadata = ResumeGenerateResponse(
        application_id=str(app_id),
        company_name=request.target_company,
        job_title=request.job_title,
        duplicate_warning=duplicate_warning,
        filename=filename,
    )

    return docx_stream, filename, metadata
