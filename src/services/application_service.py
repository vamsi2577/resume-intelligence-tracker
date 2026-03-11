"""
Application service layer.

All DB operations live here. Routes call these functions.
Never imports FastAPI — raises custom exceptions instead.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.application import ApplicationStatusHistory, JobApplication
from src.schemas.application import (
    ApplicationCreateRequest,
    ApplicationFilters,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationUpdateRequest,
    PaginationMeta,
    SortDir,
    StatusHistoryResponse,
)
from src.utils.exceptions import DuplicateError, NotFoundError
from src.utils.logger import get_logger
from src.utils.metrics import track_db_query

logger = get_logger(__name__)


# ── Helpers ───────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_history(application_id: uuid.UUID, status: str, note: str | None = None) -> ApplicationStatusHistory:
    return ApplicationStatusHistory(
        id=uuid.uuid4(),
        application_id=application_id,
        status=status,
        changed_at=_utcnow(),
        note=note,
    )


# ── Duplicate detection ───────────────────────────────────

async def _check_duplicates(
    db: AsyncSession,
    company_name: str,
    job_title: str,
    applied_date,
    job_id: str | None,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """
    Returns True if a soft duplicate warning should be raised.
    Raises DuplicateError for hard duplicates (company + job_id).
    """
    # Hard duplicate: same company + job_id
    if job_id:
        stmt = select(JobApplication).where(
            JobApplication.company_name == company_name,
            JobApplication.job_id == job_id,
        )
        if exclude_id:
            stmt = stmt.where(JobApplication.id != exclude_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            raise DuplicateError(str(existing.id))

    # Soft duplicate: same company + title + date
    stmt = select(JobApplication).where(
        JobApplication.company_name == company_name,
        JobApplication.job_title == job_title,
        JobApplication.applied_date == applied_date,
    )
    if exclude_id:
        stmt = stmt.where(JobApplication.id != exclude_id)
    result = await db.execute(stmt)
    soft_dup = result.scalar_one_or_none()
    return soft_dup is not None


# ── Service functions ─────────────────────────────────────

@track_db_query("create_application")
async def create_application(
    db: AsyncSession,
    data: ApplicationCreateRequest,
) -> ApplicationResponse:
    duplicate_warning = await _check_duplicates(
        db,
        company_name=data.company_name,
        job_title=data.job_title,
        applied_date=data.applied_date,
        job_id=data.job_id,
    )

    app = JobApplication(
        id=uuid.uuid4(),
        **data.model_dump(),
    )
    db.add(app)

    # Auto-insert first history entry
    db.add(_make_history(app.id, app.status, note="Initial status"))
    await db.flush()
    await db.refresh(app)

    logger.info(
        "Application created",
        extra={
            "application_id": str(app.id),
            "company": app.company_name,
            "duplicate_warning": duplicate_warning,
        },
    )

    response = ApplicationResponse.model_validate(app)
    response.duplicate_warning = duplicate_warning
    return response


@track_db_query("update_application")
async def update_application(
    db: AsyncSession,
    application_id: uuid.UUID,
    data: ApplicationUpdateRequest,
) -> ApplicationResponse:
    app = await db.get(JobApplication, application_id)
    if not app:
        raise NotFoundError("Application", str(application_id))

    previous_status = app.status
    updated_fields = data.model_dump(exclude_none=True)

    for field, value in updated_fields.items():
        # Convert enum to its string value for ORM assignment
        setattr(app, field, value.value if hasattr(value, "value") else value)

    # Write history only if status changed
    if "status" in updated_fields and updated_fields["status"].value != previous_status:
        db.add(_make_history(app.id, updated_fields["status"].value))

    app.updated_at = _utcnow()
    await db.flush()
    await db.refresh(app)

    logger.info(
        "Application updated",
        extra={
            "application_id": str(app.id),
            "fields": list(updated_fields.keys()),
        },
    )

    return ApplicationResponse.model_validate(app)


@track_db_query("get_application_by_id")
async def get_application_by_id(
    db: AsyncSession,
    application_id: uuid.UUID,
) -> ApplicationResponse:
    app = await db.get(JobApplication, application_id)
    if not app:
        raise NotFoundError("Application", str(application_id))
    return ApplicationResponse.model_validate(app)


@track_db_query("get_applications")
async def get_applications(
    db: AsyncSession,
    filters: ApplicationFilters,
) -> ApplicationListResponse:
    stmt = select(JobApplication)

    # ── Filters ───────────────────────────────────────────
    if filters.company:
        stmt = stmt.where(JobApplication.company_name.in_(filters.company))
    if filters.status:
        stmt = stmt.where(JobApplication.status.in_([s.value for s in filters.status]))
    if filters.source:
        stmt = stmt.where(JobApplication.source == filters.source.value)
    if filters.work_type:
        stmt = stmt.where(JobApplication.work_type == filters.work_type.value)
    if filters.job_title:
        stmt = stmt.where(JobApplication.job_title.ilike(f"%{filters.job_title}%"))
    if filters.date_from:
        stmt = stmt.where(JobApplication.applied_date >= filters.date_from)
    if filters.date_to:
        stmt = stmt.where(JobApplication.applied_date <= filters.date_to)
    if filters.ids:
        stmt = stmt.where(JobApplication.id.in_(filters.ids))

    # ── Total count ───────────────────────────────────────
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # ── Sorting ───────────────────────────────────────────
    sort_col = getattr(JobApplication, filters.sort_by.value)
    stmt = stmt.order_by(sort_col.asc() if filters.sort_dir == SortDir.asc else sort_col.desc())

    # ── Pagination ────────────────────────────────────────
    offset = (filters.page - 1) * filters.limit
    stmt = stmt.offset(offset).limit(filters.limit)

    result = await db.execute(stmt)
    apps = result.scalars().all()

    total_pages = math.ceil(total / filters.limit) if total > 0 else 0

    logger.info(
        "Applications fetched",
        extra={"total": total, "page": filters.page, "returned": len(apps)},
    )

    return ApplicationListResponse(
        data=[ApplicationResponse.model_validate(a) for a in apps],
        pagination=PaginationMeta(
            page=filters.page,
            limit=filters.limit,
            total=total,
            total_pages=total_pages,
        ),
    )


@track_db_query("get_status_history")
async def get_status_history(
    db: AsyncSession,
    application_id: uuid.UUID,
) -> list[StatusHistoryResponse]:
    # Verify application exists
    app = await db.get(JobApplication, application_id)
    if not app:
        raise NotFoundError("Application", str(application_id))

    stmt = (
        select(ApplicationStatusHistory)
        .where(ApplicationStatusHistory.application_id == application_id)
        .order_by(ApplicationStatusHistory.changed_at.asc())
    )
    result = await db.execute(stmt)
    history = result.scalars().all()

    return [StatusHistoryResponse.model_validate(h) for h in history]
