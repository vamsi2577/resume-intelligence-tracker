"""
API routes for Resume Generator.

Endpoints:
  POST /api/v1/generate-resume          — pre-structured JSON in → DOCX out
  POST /api/v1/generate-resume-from-jd  — raw JD in → tailored DOCX (or JSON preview) out
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_owner
from src.db.session import get_db
from src.schemas.resume_generator import (
    JDResumePreviewResponse,
    JDResumeRequest,
    ResumeRequest,
)
from src.services import (
    generation_audit_service,
    resume_ai_service,
    resume_generator_service,
)
from src.services.llm_client import LLMError
from src.utils.correlation import get_correlation_id
from src.utils.llm_context import get_last_generation_id, set_preview_mode
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["resume-generator"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_response(
    docx_stream, filename: str, metadata
) -> StreamingResponse:
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Application-Id": metadata.application_id,
        "X-Duplicate-Warning": str(metadata.duplicate_warning).lower(),
        "X-Metadata": json.dumps(
            {
                "application_id": metadata.application_id,
                "company_name": metadata.company_name,
                "job_title": metadata.job_title,
                "duplicate_warning": metadata.duplicate_warning,
                "filename": filename,
            }
        ),
        "Access-Control-Expose-Headers": "X-Application-Id, X-Duplicate-Warning, X-Metadata",
    }
    return StreamingResponse(docx_stream, media_type=DOCX_MEDIA_TYPE, headers=headers)


@router.post("/generate-resume", response_class=StreamingResponse)
async def generate_resume(
    request: ResumeRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Accepts pre-structured résumé JSON (legacy / ChatGPT flow).
    Generates a .docx file, logs the application, and returns the file.
    """
    docx_stream, filename, metadata = await resume_generator_service.generate_and_log(
        db, request
    )
    logger.info(
        "Resume generated and application logged",
        extra={
            "application_id": metadata.application_id,
            "company": metadata.company_name,
            "generated_filename": filename,
        },
    )
    return _docx_response(docx_stream, filename, metadata)


@router.post("/generate-resume-from-jd")
async def generate_resume_from_jd(
    request: JDResumeRequest,
    preview: bool = Query(
        False,
        description="If true, return tailored ResumeRequest JSON instead of a DOCX stream.",
    ),
    db: AsyncSession = Depends(get_db),
    owner_id: uuid.UUID = Depends(get_current_owner),
):
    """
    Tailor the owner's base résumé to a raw job description using the
    configured LLM provider.

    - Default: stream a tailored DOCX and auto-log the application
      (same contract as POST /generate-resume).
    - `preview=true`: return the tailored ResumeRequest JSON so the
      client can review/edit before committing. No DB write in preview mode.
    """
    # Recorded on the audit row so preview attempts are distinguishable
    # from committed generations.
    set_preview_mode(preview)

    try:
        tailored = await resume_ai_service.tailor(db, owner_id, request)
    except LLMError as e:
        # Upstream model failed — surface as 502, not opaque 500. Include
        # the correlation id so the failure can be traced to its audit row.
        raise HTTPException(
            status_code=502,
            detail=f"LLM upstream failure: {e}",
            headers={"X-Correlation-ID": get_correlation_id()},
        ) from e

    if preview:
        return JDResumePreviewResponse(tailored=tailored)

    docx_stream, filename, metadata = await resume_generator_service.generate_and_log(
        db, tailored
    )
    # Link the audit row written during tailoring to the application it
    # produced (best-effort; never blocks the response).
    await generation_audit_service.attach_application(
        get_last_generation_id(), uuid.UUID(metadata.application_id)
    )
    logger.info(
        "Resume generated from JD",
        extra={
            "application_id": metadata.application_id,
            "company": metadata.company_name,
            "generated_filename": filename,
            "owner_id": str(owner_id),
        },
    )
    return _docx_response(docx_stream, filename, metadata)
