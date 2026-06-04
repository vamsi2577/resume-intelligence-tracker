"""
JD → tailored ResumeRequest via the configured LLM provider.

Flow:
  1. Load the owner's base résumé (raw text).
  2. Render the prompt template with base résumé + JD + caller hints.
  3. Call llm_client.complete(json=True) and validate the result into a
     ResumeRequest Pydantic model.
  4. Caller decides whether to return the structured JSON (preview mode)
     or hand off to resume_generator_service.generate_and_log to render
     the DOCX and log the application — no duplication of those steps
     lives here.
"""
from __future__ import annotations

import uuid
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.resume_generator import JDResumeRequest, ResumeRequest
from src.services import base_resume_service, llm_client
from src.services.generation_audit_service import track_llm_call
from src.utils.exceptions import ValidationError
from src.utils.logger import get_logger

logger = get_logger(__name__)

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "resume_generator"
    / "jd_to_resume_v1.txt"
)


@lru_cache(maxsize=1)
def _prompt_template() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _render_prompt(
    *,
    base_resume: str,
    job_description: str,
    target_company_hint: str | None,
    job_title_hint: str | None,
) -> str:
    # The template contains a literal JSON schema example with `{}` braces,
    # so we use explicit substitution rather than str.format.
    return (
        _prompt_template()
        .replace("{base_resume}", base_resume)
        .replace("{job_description}", job_description)
        .replace("{target_company_hint}", target_company_hint or "(none)")
        .replace("{job_title_hint}", job_title_hint or "(none)")
    )


@track_llm_call
async def tailor(
    db: AsyncSession,
    owner_id: uuid.UUID,
    payload: JDResumeRequest,
) -> ResumeRequest:
    """Run the LLM and return a validated ResumeRequest.

    Every attempt (success or failure) is recorded to resume_generations
    by the @track_llm_call decorator.

    Raises:
        NotFoundError if the owner has not uploaded a base résumé.
        ValidationError if the LLM output cannot be coerced into ResumeRequest.
        LLMError on upstream failure (let the route map it to 502).
    """
    base = await base_resume_service.get_required(db, owner_id)

    prompt = _render_prompt(
        base_resume=base.raw_text,
        job_description=payload.job_description,
        target_company_hint=payload.target_company,
        job_title_hint=payload.job_title,
    )

    logger.info(
        "Tailoring résumé from JD",
        extra={
            "owner_id": str(owner_id),
            "jd_chars": len(payload.job_description),
            "hint_company": payload.target_company,
            "hint_title": payload.job_title,
        },
    )
    raw = await llm_client.complete(
        prompt,
        system=(
            "You are a deterministic JSON generator. Respond with a single "
            "JSON object only — no markdown, no commentary."
        ),
        json=True,
    )

    # Ensure top-level identity fields are present even if the LLM dropped
    # them. The caller's hints take precedence; otherwise fall back to the
    # JD text itself.
    if payload.target_company:
        raw["target_company"] = payload.target_company
    elif not raw.get("target_company"):
        raw["target_company"] = "Unknown"

    if payload.job_title:
        raw["job_title"] = payload.job_title
    elif not raw.get("job_title"):
        raw["job_title"] = "Unknown Role"

    # Always use the original JD — never trust the LLM's echo, which may
    # be truncated or paraphrased. This is what gets stored on the
    # application record.
    raw["job_description"] = payload.job_description

    try:
        return ResumeRequest.model_validate(raw)
    except PydanticValidationError as e:
        logger.error(
            "LLM output failed ResumeRequest validation",
            extra={"errors": e.errors()[:3]},
        )
        raise ValidationError(
            f"LLM output did not match the résumé schema: {e.errors()[:3]}"
        ) from e
