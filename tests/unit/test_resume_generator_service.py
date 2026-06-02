"""
Unit tests for resume_generator_service.

DB and docx_builder are fully mocked — no live DB or file I/O.

Run:  pytest tests/unit/test_resume_generator_service.py -v
"""
from __future__ import annotations

import io
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.resume_generator import (
    CertificationItem,
    EducationItem,
    ExperienceItem,
    ResumeRequest,
    SkillCategory,
    SummaryObject,
)


# ── Fixtures ──────────────────────────────────────────────

def _minimal_request(**overrides) -> ResumeRequest:
    base = dict(
        target_company="Acme Corp",
        job_title="Senior Software Engineer",
        job_description="We are looking for a senior engineer...",
        full_name="Test User",
        contact_info="test@example.com",
    )
    base.update(overrides)
    return ResumeRequest(**base)


def _full_request() -> ResumeRequest:
    return ResumeRequest(
        target_company="Acme Corp",
        job_title="Senior Software Engineer",
        job_description="Full JD text here...",
        full_name="Test User",
        contact_info="test@example.com",
        summary=SummaryObject(
            summary_text="Experienced engineer specializing in **cloud** systems.",
            summary_points=["Expert in **Python** and **FastAPI**."],
        ),
        skills=[SkillCategory(category="Languages", items=["Python", "Java"])],
        experience=[
            ExperienceItem(
                title="Software Engineer",
                company="Acme Corp",
                date="Jan 2024 – Present",
                bullets=["Built scalable **APIs** with FastAPI."],
                tools=["Python", "FastAPI"],
            )
        ],
        certifications=[CertificationItem(name="AWS Solutions Architect")],
        education=[
            EducationItem(
                degree="M.S. Computer Science",
                university="Lamar University",
                details="GPA: 3.8",
            )
        ],
    )


def _make_db(existing_app=None) -> AsyncMock:
    db = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalars = MagicMock(
        return_value=MagicMock(first=MagicMock(return_value=existing_app))
    )
    db.execute = AsyncMock(return_value=exec_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


FAKE_STREAM = io.BytesIO(b"fake-docx-content")
FAKE_FILENAME = "Acme_Corp_Redacted_Resume.docx"


# ── generate_and_log ──────────────────────────────────────

class TestGenerateAndLog:

    @pytest.mark.asyncio
    async def test_returns_stream_filename_metadata(self):
        from src.services.resume_generator_service import generate_and_log
        db = _make_db()

        with patch("src.services.resume_generator_service.build_docx", return_value=FAKE_STREAM), \
             patch("src.services.resume_generator_service.build_filename", return_value=FAKE_FILENAME):
            stream, filename, metadata = await generate_and_log(db, _minimal_request())

        assert stream is FAKE_STREAM
        assert filename == FAKE_FILENAME
        assert metadata.company_name == "Acme Corp"
        assert metadata.job_title == "Senior Software Engineer"

    @pytest.mark.asyncio
    async def test_application_added_to_db(self):
        from src.services.resume_generator_service import generate_and_log
        db = _make_db()

        with patch("src.services.resume_generator_service.build_docx", return_value=FAKE_STREAM), \
             patch("src.services.resume_generator_service.build_filename", return_value=FAKE_FILENAME):
            await generate_and_log(db, _minimal_request())

        # add() called at least twice: application + history
        assert db.add.call_count >= 2

    @pytest.mark.asyncio
    async def test_flush_called(self):
        from src.services.resume_generator_service import generate_and_log
        db = _make_db()

        with patch("src.services.resume_generator_service.build_docx", return_value=FAKE_STREAM), \
             patch("src.services.resume_generator_service.build_filename", return_value=FAKE_FILENAME):
            await generate_and_log(db, _minimal_request())

        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_duplicate_warning_on_new_application(self):
        from src.services.resume_generator_service import generate_and_log
        db = _make_db(existing_app=None)

        with patch("src.services.resume_generator_service.build_docx", return_value=FAKE_STREAM), \
             patch("src.services.resume_generator_service.build_filename", return_value=FAKE_FILENAME):
            _, _, metadata = await generate_and_log(db, _minimal_request())

        assert metadata.duplicate_warning is False

    @pytest.mark.asyncio
    async def test_duplicate_warning_on_existing_application(self):
        from src.services.resume_generator_service import generate_and_log
        existing = MagicMock()
        existing.id = uuid.uuid4()
        db = _make_db(existing_app=existing)

        with patch("src.services.resume_generator_service.build_docx", return_value=FAKE_STREAM), \
             patch("src.services.resume_generator_service.build_filename", return_value=FAKE_FILENAME):
            _, _, metadata = await generate_and_log(db, _minimal_request())

        assert metadata.duplicate_warning is True

    @pytest.mark.asyncio
    async def test_application_id_is_valid_uuid(self):
        from src.services.resume_generator_service import generate_and_log
        db = _make_db()

        with patch("src.services.resume_generator_service.build_docx", return_value=FAKE_STREAM), \
             patch("src.services.resume_generator_service.build_filename", return_value=FAKE_FILENAME):
            _, _, metadata = await generate_and_log(db, _minimal_request())

        uuid.UUID(metadata.application_id)  # raises if invalid

    @pytest.mark.asyncio
    async def test_job_description_stored(self):
        from src.services.resume_generator_service import generate_and_log
        db = _make_db()
        request = _minimal_request(job_description="Looking for Python engineer...")

        with patch("src.services.resume_generator_service.build_docx", return_value=FAKE_STREAM), \
             patch("src.services.resume_generator_service.build_filename", return_value=FAKE_FILENAME):
            await generate_and_log(db, request)

        # Capture the JobApplication added to DB and verify job_description
        added_app = db.add.call_args_list[0][0][0]
        assert added_app.job_description == "Looking for Python engineer..."

    @pytest.mark.asyncio
    async def test_resume_content_stored_as_dict(self):
        from src.services.resume_generator_service import generate_and_log
        db = _make_db()

        with patch("src.services.resume_generator_service.build_docx", return_value=FAKE_STREAM), \
             patch("src.services.resume_generator_service.build_filename", return_value=FAKE_FILENAME):
            await generate_and_log(db, _full_request())

        added_app = db.add.call_args_list[0][0][0]
        assert isinstance(added_app.resume_content, dict)
        assert added_app.resume_content["target_company"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_source_is_resume_generator(self):
        from src.services.resume_generator_service import generate_and_log
        db = _make_db()

        with patch("src.services.resume_generator_service.build_docx", return_value=FAKE_STREAM), \
             patch("src.services.resume_generator_service.build_filename", return_value=FAKE_FILENAME):
            await generate_and_log(db, _minimal_request())

        added_app = db.add.call_args_list[0][0][0]
        assert added_app.source == "resume_generator"

    @pytest.mark.asyncio
    async def test_status_is_applied(self):
        from src.services.resume_generator_service import generate_and_log
        db = _make_db()

        with patch("src.services.resume_generator_service.build_docx", return_value=FAKE_STREAM), \
             patch("src.services.resume_generator_service.build_filename", return_value=FAKE_FILENAME):
            await generate_and_log(db, _minimal_request())

        added_app = db.add.call_args_list[0][0][0]
        assert added_app.status == "applied"

    @pytest.mark.asyncio
    async def test_applied_date_is_today(self):
        from src.services.resume_generator_service import generate_and_log
        db = _make_db()

        with patch("src.services.resume_generator_service.build_docx", return_value=FAKE_STREAM), \
             patch("src.services.resume_generator_service.build_filename", return_value=FAKE_FILENAME):
            await generate_and_log(db, _minimal_request())

        added_app = db.add.call_args_list[0][0][0]
        assert added_app.applied_date == date.today()


# ── Schema validation ─────────────────────────────────────

class TestResumeRequestSchema:

    def test_target_company_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ResumeRequest(job_title="Engineer")

    def test_job_title_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ResumeRequest(target_company="Acme")

    def test_job_description_optional(self):
        req = ResumeRequest(
            target_company="Acme",
            job_title="Engineer",
            full_name="Test User",
            contact_info="test@example.com",
        )
        assert req.job_description is None

    def test_full_request_valid(self):
        req = _full_request()
        assert req.target_company == "Acme Corp"
        assert req.job_title == "Senior Software Engineer"
        assert req.summary is not None
        assert len(req.skills) == 1
        assert len(req.experience) == 1

    def test_empty_company_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ResumeRequest(
                target_company="",
                job_title="Engineer",
                full_name="Test User",
                contact_info="test@example.com",
            )

    def test_empty_job_title_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ResumeRequest(
                target_company="Acme",
                job_title="",
                full_name="Test User",
                contact_info="test@example.com",
            )
