"""
Application service layer.

All DB operations live here. Routes call these functions.
Never imports FastAPI — raises custom exceptions instead.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone, date, timedelta

from sqlalchemy import func, select, or_, and_
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
    StatsResponse,
    StatusHistoryResponse,
    WeeklyTrendPoint,
    SourceBreakdown,
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


async def _get_owned(
    db: AsyncSession, application_id: uuid.UUID, owner_id: uuid.UUID
) -> JobApplication:
    """Fetch an application scoped to its owner.

    Replaces a bare `db.get(...)` PK lookup: a row owned by a different
    tenant resolves to NotFoundError (→ 404), never leaking that it exists
    (closes the IDOR).
    """
    stmt = select(JobApplication).where(
        JobApplication.id == application_id,
        JobApplication.owner_id == owner_id,
    )
    app = (await db.execute(stmt)).scalar_one_or_none()
    if app is None:
        raise NotFoundError("Application", str(application_id))
    return app


# ── Duplicate detection ───────────────────────────────────

async def _check_duplicates(
    db: AsyncSession,
    owner_id: uuid.UUID,
    company_name: str,
    job_title: str,
    applied_date,
    job_id: str | None,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """
    Returns True if a soft duplicate warning should be raised.
    Raises DuplicateError for hard duplicates (company + job_id).

    Duplicate detection is per-owner: User B's "JOB123" never collides with
    User A's.
    """
    # Hard duplicate: same company + job_id (ignore soft-deleted rows so
    # the user can re-apply after deleting the old entry).
    if job_id:
        stmt = select(JobApplication).where(
            JobApplication.owner_id == owner_id,
            JobApplication.company_name == company_name,
            JobApplication.job_id == job_id,
            JobApplication.is_deleted == False,  # noqa: E712
        )
        if exclude_id:
            stmt = stmt.where(JobApplication.id != exclude_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            raise DuplicateError(str(existing.id))

    # Soft duplicate: same company + title + date
    stmt = select(JobApplication).where(
        JobApplication.owner_id == owner_id,
        JobApplication.company_name == company_name,
        JobApplication.job_title == job_title,
        JobApplication.applied_date == applied_date,
        JobApplication.is_deleted == False,  # noqa: E712
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
    owner_id: uuid.UUID,
) -> ApplicationResponse:
    duplicate_warning = await _check_duplicates(
        db,
        owner_id=owner_id,
        company_name=data.company_name,
        job_title=data.job_title,
        applied_date=data.applied_date,
        job_id=data.job_id,
    )

    app = JobApplication(
        id=uuid.uuid4(),
        owner_id=owner_id,
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
    owner_id: uuid.UUID,
) -> ApplicationResponse:
    app = await _get_owned(db, application_id, owner_id)

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
    owner_id: uuid.UUID,
) -> ApplicationResponse:
    app = await _get_owned(db, application_id, owner_id)
    return ApplicationResponse.model_validate(app)


@track_db_query("get_applications")
async def get_applications(
    db: AsyncSession,
    filters: ApplicationFilters,
    owner_id: uuid.UUID,
) -> ApplicationListResponse:
    # Tenant scope first — everything below filters within the owner's rows.
    stmt = select(JobApplication).where(JobApplication.owner_id == owner_id)

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
    if filters.search:
        pattern = f"%{filters.search}%"
        stmt = stmt.where(
            or_(
                JobApplication.company_name.ilike(pattern),
                JobApplication.job_title.ilike(pattern),
            )
        )
    if not filters.include_deleted:
        stmt = stmt.where(JobApplication.is_deleted == False)  # noqa: E712
    if filters.date_from:
        stmt = stmt.where(JobApplication.applied_date >= filters.date_from)
    if filters.date_to:
        stmt = stmt.where(JobApplication.applied_date <= filters.date_to)
    if filters.ids:
        stmt = stmt.where(JobApplication.id.in_(filters.ids))
    if filters.needs_review is not None:
        stmt = stmt.where(JobApplication.needs_review == filters.needs_review)

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


@track_db_query("get_stats")
async def get_stats(db: AsyncSession, owner_id: uuid.UUID) -> StatsResponse:
    """Aggregated dashboard metrics. Soft-deleted rows are excluded.

    Scoped to the owner — one tenant's stats never include another's rows.
    """
    base_where = and_(
        JobApplication.owner_id == owner_id,
        JobApplication.is_deleted == False,  # noqa: E712
    )

    # ── 1. Headline counts ────────────────────────────────
    counts_stmt = select(
        func.count().label("total"),
        func.count().filter(JobApplication.status == "interview").label("interview"),
        func.count().filter(JobApplication.status == "assessment").label("assessment"),
        func.count().filter(JobApplication.status == "rejected").label("rejected"),
        func.count().filter(JobApplication.status == "offer").label("offer"),
        func.count().filter(JobApplication.needs_review == True).label("needs_review"),
    ).select_from(JobApplication).where(base_where)
    row = (await db.execute(counts_stmt)).one()

    # ── 2. Source breakdown ───────────────────────────────
    src_stmt = (
        select(JobApplication.source, func.count())
        .where(base_where)
        .group_by(JobApplication.source)
    )
    src_rows = (await db.execute(src_stmt)).all()
    src_counts = {src: cnt for src, cnt in src_rows}
    source_breakdown = SourceBreakdown(
        manual=src_counts.get("manual", 0),
        resume_generator=src_counts.get("resume_generator", 0),
    )

    # ── 3. Weekly trend (last 12 ISO weeks) ───────────────
    today = date.today()
    twelve_weeks_ago = today - timedelta(weeks=11)  # inclusive of current week
    trend_stmt = (
        select(
            func.date_trunc("week", JobApplication.applied_date).label("week"),
            func.count().label("count"),
        )
        .where(base_where)
        .where(JobApplication.applied_date >= twelve_weeks_ago)
        .group_by("week")
        .order_by("week")
    )
    trend_rows = (await db.execute(trend_stmt)).all()
    weekly_trend = [
        WeeklyTrendPoint(
            # date_trunc returns a datetime; .date() flattens for the schema
            week=(w.date() if hasattr(w, "date") else w),
            count=c,
        )
        for w, c in trend_rows
    ]

    # ── 4. ATS pass rate ──────────────────────────────────
    # Fraction of applications that advanced past initial screening, i.e.
    # reached assessment / interview / offer. Useful as a leading indicator
    # of résumé fit. Zero on empty data.
    advanced = row.assessment + row.interview + row.offer
    ats_pass_rate = (advanced / row.total) if row.total else 0.0

    logger.info(
        "Stats fetched",
        extra={"total": row.total, "ats_pass_rate": ats_pass_rate},
    )
    return StatsResponse(
        total=row.total,
        interview=row.interview,
        rejected=row.rejected,
        offer=row.offer,
        needs_review=row.needs_review,
        ats_pass_rate=ats_pass_rate,
        source_breakdown=source_breakdown,
        weekly_trend=weekly_trend,
    )


@track_db_query("delete_application")
async def delete_application(
    db: AsyncSession,
    application_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> ApplicationResponse:
    """Soft-delete: set is_deleted=true and append a history note.

    Hard deletes are intentionally not exposed; callers can re-list with
    ApplicationFilters.include_deleted=True to recover a row.
    """
    app = await _get_owned(db, application_id, owner_id)
    if app.is_deleted:
        # Idempotent: deleting an already-deleted row is a no-op.
        return ApplicationResponse.model_validate(app)

    app.is_deleted = True
    app.updated_at = _utcnow()
    db.add(_make_history(app.id, app.status, note="Soft-deleted"))
    await db.flush()
    await db.refresh(app)

    logger.info("Application soft-deleted", extra={"application_id": str(app.id)})
    return ApplicationResponse.model_validate(app)


@track_db_query("get_application_resume_content")
async def get_resume_content(
    db: AsyncSession,
    application_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> dict:
    """Return the stored ResumeRequest JSON for re-rendering as DOCX.

    Raises NotFoundError if the application doesn't exist, belongs to another
    owner, or was logged without `resume_content` (e.g. created via the manual
    `log-application` flow, no résumé generation).
    """
    app = await _get_owned(db, application_id, owner_id)
    if not app.resume_content:
        raise NotFoundError("ResumeContent", str(application_id))
    return app.resume_content


@track_db_query("get_status_history")
async def get_status_history(
    db: AsyncSession,
    application_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> list[StatusHistoryResponse]:
    # Verify the application exists AND belongs to this owner before reading
    # its history (history has no owner_id of its own — it inherits via parent).
    await _get_owned(db, application_id, owner_id)

    stmt = (
        select(ApplicationStatusHistory)
        .where(ApplicationStatusHistory.application_id == application_id)
        .order_by(ApplicationStatusHistory.changed_at.asc())
    )
    result = await db.execute(stmt)
    history = result.scalars().all()

    return [StatusHistoryResponse.model_validate(h) for h in history]
