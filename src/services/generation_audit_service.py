"""
Résumé-generation audit logging.

Provides:
  - `track_llm_call`  — decorator for resume_ai_service.tailor that records
    one resume_generations row per attempt (success or failure), capturing
    LLM telemetry (model, tokens, latency) from the llm_context ContextVar.
  - `attach_application` — backfill application_id onto the audit row once
    the application has been logged (the audit row is written during the
    LLM step, before the application exists).
  - `list_recent` / `get_stats` — read side for the dashboard history view.

Audit rows are written from an INDEPENDENT session so a failure row
survives even though get_db() rolls the request session back on the
exception. The decorator never raises on its own (a logging failure must
not mask the real result/error).
"""
from __future__ import annotations

import functools
import time
import uuid
from typing import Awaitable, Callable

from sqlalchemy import select, update

from src.db.session import AsyncSessionFactory
from src.models.resume_generation import ResumeGeneration
from src.schemas.resume_generation import GenerationStatsResponse
from src.services.llm_client import LLMError
from src.utils.correlation import get_correlation_id
from src.utils.exceptions import NotFoundError, ValidationError
from src.utils.llm_context import (
    get_llm_meta,
    get_preview_mode,
    reset_llm_meta,
    set_last_generation_id,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Cap raw output we persist on failure so a runaway response can't bloat
# the table. Enough to debug a malformed JSON payload.
_MAX_RAW_OUTPUT = 20_000


async def _persist(
    *,
    owner_id: uuid.UUID | None,
    payload,
    status: str,
    error_message: str | None = None,
    wrapper_ms: int,
) -> uuid.UUID | None:
    """Write one audit row from an independent session. Never raises."""
    meta = get_llm_meta()
    duration_ms = (meta.duration_ms if meta and meta.duration_ms else wrapper_ms)
    raw_output = None
    if status != "success" and meta and meta.raw_content:
        raw_output = meta.raw_content[:_MAX_RAW_OUTPUT]

    row = ResumeGeneration(
        id=uuid.uuid4(),
        owner_id=owner_id,
        correlation_id=get_correlation_id() or None,
        status=status,
        target_company=getattr(payload, "target_company", None),
        job_title=getattr(payload, "job_title", None),
        jd_chars=len(getattr(payload, "job_description", "") or ""),
        preview=get_preview_mode(),
        provider=(meta.provider if meta else None),
        model=(meta.model if meta else None),
        prompt_tokens=(meta.prompt_tokens if meta else None),
        completion_tokens=(meta.completion_tokens if meta else None),
        total_tokens=(meta.total_tokens if meta else None),
        duration_ms=duration_ms,
        error_message=error_message,
        llm_raw_output=raw_output,
    )
    try:
        async with AsyncSessionFactory() as session:
            session.add(row)
            await session.commit()
        set_last_generation_id(row.id)
        return row.id
    except Exception:  # pragma: no cover - logging must not mask the result
        logger.error(
            "Failed to write resume_generations audit row",
            extra={"status": status, "correlation_id": get_correlation_id()},
            exc_info=True,
        )
        return None


def track_llm_call(fn: Callable[..., Awaitable]) -> Callable[..., Awaitable]:
    """Wrap `tailor(db, owner_id, payload)` to audit every attempt.

    NotFoundError (no base résumé on file) is NOT audited — nothing was
    generated. LLMError and ValidationError are recorded as failures with
    the raw model output attached for debugging.
    """

    @functools.wraps(fn)
    async def wrapper(db, owner_id, payload, *args, **kwargs):
        reset_llm_meta()
        start = time.perf_counter()
        try:
            result = await fn(db, owner_id, payload, *args, **kwargs)
        except NotFoundError:
            raise
        except LLMError as e:
            await _persist(
                owner_id=owner_id, payload=payload, status="llm_error",
                error_message=str(e),
                wrapper_ms=int((time.perf_counter() - start) * 1000),
            )
            raise
        except ValidationError as e:
            await _persist(
                owner_id=owner_id, payload=payload, status="validation_error",
                error_message=str(e),
                wrapper_ms=int((time.perf_counter() - start) * 1000),
            )
            raise
        else:
            await _persist(
                owner_id=owner_id, payload=payload, status="success",
                wrapper_ms=int((time.perf_counter() - start) * 1000),
            )
            return result

    return wrapper


async def attach_application(
    generation_id: uuid.UUID | None, application_id: uuid.UUID
) -> None:
    """Backfill application_id onto a success row. Best-effort."""
    if not generation_id:
        return
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(
                update(ResumeGeneration)
                .where(ResumeGeneration.id == generation_id)
                .values(application_id=application_id)
            )
            await session.commit()
    except Exception:  # pragma: no cover
        logger.error(
            "Failed to attach application_id to audit row",
            extra={"generation_id": str(generation_id)},
            exc_info=True,
        )


async def list_recent(db, *, limit: int = 50) -> list[ResumeGeneration]:
    stmt = (
        select(ResumeGeneration)
        .order_by(ResumeGeneration.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_stats(db) -> GenerationStatsResponse:
    rows = (await db.execute(select(ResumeGeneration))).scalars().all()
    total = len(rows)
    if total == 0:
        return GenerationStatsResponse()

    success = sum(1 for r in rows if r.status == "success")
    llm_error = sum(1 for r in rows if r.status == "llm_error")
    validation_error = sum(1 for r in rows if r.status == "validation_error")
    durations = [r.duration_ms for r in rows if r.duration_ms is not None]
    total_tokens = sum(r.total_tokens or 0 for r in rows)

    return GenerationStatsResponse(
        total=total,
        success=success,
        llm_error=llm_error,
        validation_error=validation_error,
        success_rate=round(success / total, 3),
        avg_duration_ms=int(sum(durations) / len(durations)) if durations else None,
        total_tokens=total_tokens,
    )
