"""
API routes for job applications.

Endpoints:
  POST   /api/v1/log-application
  PATCH  /api/v1/log-application/{id}
  GET    /api/v1/applications
  GET    /api/v1/applications/{id}
  GET    /api/v1/applications/{id}/history
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.application import (
    ApplicationCreateRequest,
    ApplicationFilters,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationSource,
    ApplicationStatus,
    ApplicationUpdateRequest,
    SortDir,
    SortField,
    StatsResponse,
    StatusHistoryResponse,
    WorkType,
)
from src.services import application_service
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["applications"])


# ── Query params → ApplicationFilters dependency ──────────

def _parse_filters(
    company: Annotated[Optional[List[str]], Query()] = None,
    status: Annotated[Optional[List[ApplicationStatus]], Query()] = None,
    source: Annotated[Optional[ApplicationSource], Query()] = None,
    work_type: Annotated[Optional[WorkType], Query()] = None,
    job_title: Annotated[Optional[str], Query()] = None,
    search: Annotated[Optional[str], Query()] = None,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
    ids: Annotated[Optional[List[uuid.UUID]], Query()] = None,
    needs_review: Annotated[Optional[bool], Query()] = None,
    include_deleted: Annotated[bool, Query()] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[SortField, Query()] = SortField.applied_date,
    sort_dir: Annotated[SortDir, Query()] = SortDir.desc,
) -> ApplicationFilters:
    try:
        return ApplicationFilters(
            company=company or [],
            status=status or [],
            source=source,
            work_type=work_type,
            job_title=job_title,
            search=search,
            date_from=date_from,
            date_to=date_to,
            ids=ids or [],
            needs_review=needs_review,
            include_deleted=include_deleted,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except PydanticValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=[{k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                     for k, v in err.items()} for err in e.errors()],
        )


# ── Routes ────────────────────────────────────────────────

@router.post(
    "/log-application",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def log_application(
    body: ApplicationCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    return await application_service.create_application(db, body)


@router.patch(
    "/log-application/{application_id}",
    response_model=ApplicationResponse,
    status_code=status.HTTP_200_OK,
)
async def update_application(
    application_id: uuid.UUID,
    body: ApplicationUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    return await application_service.update_application(db, application_id, body)


@router.get(
    "/applications/stats",
    response_model=StatsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_stats(
    db: AsyncSession = Depends(get_db),
):
    return await application_service.get_stats(db)


@router.get(
    "/applications",
    response_model=ApplicationListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_applications(
    filters: ApplicationFilters = Depends(_parse_filters),
    db: AsyncSession = Depends(get_db),
):
    return await application_service.get_applications(db, filters)


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationResponse,
    status_code=status.HTTP_200_OK,
)
async def get_application(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    return await application_service.get_application_by_id(db, application_id)


@router.get(
    "/applications/{application_id}/history",
    response_model=list[StatusHistoryResponse],
    status_code=status.HTTP_200_OK,
)
async def get_application_history(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    return await application_service.get_status_history(db, application_id)


@router.delete(
    "/applications/{application_id}",
    response_model=ApplicationResponse,
    status_code=status.HTTP_200_OK,
)
async def soft_delete_application(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete: marks `is_deleted=true`. List endpoint hides it by
    default; pass `?include_deleted=true` to recover."""
    return await application_service.delete_application(db, application_id)


@router.get(
    "/applications/{application_id}/resume",
    response_class=StreamingResponse,
)
async def download_application_resume(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Re-render the stored résumé JSON as a DOCX for download.

    Only works on applications created via the résumé generator
    (those have `resume_content` populated). Returns 404 otherwise.
    """
    # Local import — avoids a top-level cycle with resume_generator paths
    # and keeps the docx dependency optional for callers who don't use it.
    from src.schemas.resume_generator import ResumeRequest
    from src.utils.docx_builder import build_docx, build_filename

    content = await application_service.get_resume_content(db, application_id)
    payload = ResumeRequest.model_validate(content)
    docx_stream = build_docx(payload)
    filename = build_filename(payload)
    return StreamingResponse(
        docx_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
