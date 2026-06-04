"""
Unit tests for resume_ai_service.

LLM client and base_resume_service are mocked — no live LLM, no DB.

Run:  pytest tests/unit/test_resume_ai_service.py -v
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.resume_generator import JDResumeRequest, ResumeRequest
from src.services import resume_ai_service
from src.utils.exceptions import ValidationError


OWNER = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _mock_base_row(raw_text: str = "Vamsi P. — Software Engineer\nPython, FastAPI, AWS"):
    row = MagicMock()
    row.raw_text = raw_text
    return row


def _well_formed_llm_output(target_company="Acme", job_title="Senior Engineer") -> dict:
    """Mirror the structured-mode JSON the LLM is asked to produce."""
    return {
        "target_company": target_company,
        "job_title": job_title,
        "job_description": "Build distributed services at scale.",
        "summary": {
            "summary_text": "Engineer specialising in **distributed systems**.",
            "summary_points": ["Strong **Python** and **FastAPI**."],
        },
        "skills": [{"category": "Languages", "items": ["Python", "Go"]}],
        "experience": [
            {
                "title": "Software Engineer",
                "company": "AdventHealth",
                "date": "2024 – Present",
                "bullets": ["Cut latency by **40%** with **Redis**."],
                "tools": ["Python", "Redis"],
            }
        ],
        "certifications": [{"name": "AWS SAA"}],
        "education": [
            {"degree": "M.S. CS", "university": "Lamar University", "details": "Distributed Systems"}
        ],
    }


@pytest.mark.asyncio
async def test_tailor_happy_path():
    """LLM JSON → ResumeRequest with caller hints applied."""
    db = AsyncMock()
    payload = JDResumeRequest(
        job_description="A long job description text describing the role.",
        target_company="OverrideCo",
        job_title="Staff Engineer",
    )

    with patch(
        "src.services.resume_ai_service.base_resume_service.get_required",
        new=AsyncMock(return_value=_mock_base_row()),
    ), patch(
        "src.services.resume_ai_service.llm_client.complete",
        new=AsyncMock(return_value=_well_formed_llm_output()),
    ) as mock_complete:
        result = await resume_ai_service.tailor(db, OWNER, payload)

    assert isinstance(result, ResumeRequest)
    # Caller hints must override the LLM's extraction.
    assert result.target_company == "OverrideCo"
    assert result.job_title == "Staff Engineer"
    # JD text is forwarded so the logged application has it on file.
    assert payload.job_description in result.job_description
    # The prompt actually contained the base résumé text and the JD.
    prompt_arg = mock_complete.call_args.args[0]
    assert "Vamsi P." in prompt_arg
    assert payload.job_description in prompt_arg


@pytest.mark.asyncio
async def test_tailor_fills_missing_top_level_fields():
    """If LLM forgets target_company / job_title, we don't crash."""
    db = AsyncMock()
    payload = JDResumeRequest(
        job_description="A long job description text describing the role.",
    )
    bad = _well_formed_llm_output()
    bad.pop("target_company")
    bad.pop("job_title")
    bad.pop("job_description")

    with patch(
        "src.services.resume_ai_service.base_resume_service.get_required",
        new=AsyncMock(return_value=_mock_base_row()),
    ), patch(
        "src.services.resume_ai_service.llm_client.complete",
        new=AsyncMock(return_value=bad),
    ):
        result = await resume_ai_service.tailor(db, OWNER, payload)

    assert result.target_company == "Unknown"
    assert result.job_title == "Unknown Role"
    assert result.job_description == payload.job_description


@pytest.mark.asyncio
async def test_tailor_invalid_llm_output_raises_validation_error():
    """If the LLM emits JSON that violates the schema, surface ValidationError."""
    db = AsyncMock()
    payload = JDResumeRequest(
        job_description="A long job description text describing the role.",
    )
    # `skills[].items` must be a list of strings; pass an int to break it.
    broken = _well_formed_llm_output()
    broken["skills"] = [{"category": "Languages", "items": [123, None]}]

    with patch(
        "src.services.resume_ai_service.base_resume_service.get_required",
        new=AsyncMock(return_value=_mock_base_row()),
    ), patch(
        "src.services.resume_ai_service.llm_client.complete",
        new=AsyncMock(return_value=broken),
    ):
        with pytest.raises(ValidationError):
            await resume_ai_service.tailor(db, OWNER, payload)


@pytest.mark.asyncio
async def test_tailor_extracts_job_metadata():
    """job_metadata from the LLM flows through onto the ResumeRequest."""
    db = AsyncMock()
    payload = JDResumeRequest(
        job_description="A long job description text describing the role.",
    )
    out = _well_formed_llm_output()
    out["job_metadata"] = {
        "location": "Austin, TX",
        "work_type": "Hybrid",          # mixed case → normalised to "hybrid"
        "salary_range": "$140k–$170k",
        "notes": "Requires US work authorization.",
    }

    with patch(
        "src.services.resume_ai_service.base_resume_service.get_required",
        new=AsyncMock(return_value=_mock_base_row()),
    ), patch(
        "src.services.resume_ai_service.llm_client.complete",
        new=AsyncMock(return_value=out),
    ):
        result = await resume_ai_service.tailor(db, OWNER, payload)

    assert result.job_metadata is not None
    assert result.job_metadata.location == "Austin, TX"
    assert result.job_metadata.work_type == "hybrid"
    assert result.job_metadata.salary_range == "$140k–$170k"
    assert "authorization" in result.job_metadata.notes


@pytest.mark.asyncio
async def test_tailor_drops_invalid_work_type():
    """An out-of-vocabulary work_type is coerced to None, not a 422."""
    db = AsyncMock()
    payload = JDResumeRequest(
        job_description="A long job description text describing the role.",
    )
    out = _well_formed_llm_output()
    out["job_metadata"] = {"work_type": "flexible", "location": ""}

    with patch(
        "src.services.resume_ai_service.base_resume_service.get_required",
        new=AsyncMock(return_value=_mock_base_row()),
    ), patch(
        "src.services.resume_ai_service.llm_client.complete",
        new=AsyncMock(return_value=out),
    ):
        result = await resume_ai_service.tailor(db, OWNER, payload)

    assert result.job_metadata.work_type is None
    assert result.job_metadata.location is None  # "" → None


@pytest.mark.asyncio
async def test_tailor_propagates_missing_base_resume():
    """No base résumé on file → NotFoundError bubbles up unchanged."""
    from src.utils.exceptions import NotFoundError

    db = AsyncMock()
    payload = JDResumeRequest(
        job_description="A long job description text describing the role.",
    )

    with patch(
        "src.services.resume_ai_service.base_resume_service.get_required",
        new=AsyncMock(side_effect=NotFoundError("base_resume", str(OWNER))),
    ):
        with pytest.raises(NotFoundError):
            await resume_ai_service.tailor(db, OWNER, payload)
