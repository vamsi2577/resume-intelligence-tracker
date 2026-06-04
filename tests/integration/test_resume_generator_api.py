"""
Integration tests for the résumé-generator API routes.

  POST /api/v1/generate-resume          — pre-structured JSON → DOCX
  POST /api/v1/generate-resume-from-jd  — raw JD → DOCX (or JSON preview)

The service layer (LLM tailoring, DOCX build, audit) is mocked — no live
DB or LLM provider is touched.

Run:  pytest tests/integration/test_resume_generator_api.py -v
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.resume_generator import ResumeRequest
from src.services.llm_client import LLMError
from src.utils.exceptions import NotFoundError, ValidationError


def _metadata(**over) -> SimpleNamespace:
    base = dict(
        application_id=str(uuid.uuid4()),
        company_name="Acme Corp",
        job_title="Senior Engineer",
        duplicate_warning=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _docx_stream():
    # StreamingResponse only needs an iterable of bytes.
    return iter([b"PK\x03\x04 fake-docx-bytes"])


def _tailored() -> ResumeRequest:
    return ResumeRequest(target_company="Acme Corp", job_title="Senior Engineer")


def _jd_body(**over) -> dict:
    base = dict(
        job_description="We are hiring a senior backend engineer with Python and async experience.",
        target_company="Acme Corp",
        job_title="Senior Engineer",
    )
    base.update(over)
    return base


# ── POST /api/v1/generate-resume (legacy structured JSON) ──

class TestGenerateResume:
    @pytest.mark.asyncio
    async def test_returns_docx_with_headers(self, client):
        with patch("src.api.resume_generator.resume_generator_service.generate_and_log",
                   new_callable=AsyncMock,
                   return_value=(_docx_stream(), "resume.docx", _metadata())):
            resp = await client.post(
                "/api/v1/generate-resume",
                json={"target_company": "Acme Corp", "job_title": "Senior Engineer"},
            )
        assert resp.status_code == 200
        assert "x-application-id" in resp.headers
        assert resp.headers["content-disposition"].endswith('filename="resume.docx"')

    @pytest.mark.asyncio
    async def test_missing_required_field_returns_422(self, client):
        resp = await client.post("/api/v1/generate-resume",
                                 json={"job_title": "Engineer"})
        assert resp.status_code == 422


# ── POST /api/v1/generate-resume-from-jd ──────────────────

class TestGenerateResumeFromJD:
    @pytest.mark.asyncio
    async def test_preview_returns_tailored_json(self, client):
        with patch("src.api.resume_generator.resume_ai_service.tailor",
                   new_callable=AsyncMock, return_value=_tailored()):
            resp = await client.post(
                "/api/v1/generate-resume-from-jd?preview=true",
                json=_jd_body(),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tailored"]["target_company"] == "Acme Corp"
        # No DOCX content type in preview mode.
        assert resp.headers["content-type"].startswith("application/json")

    @pytest.mark.asyncio
    async def test_default_streams_docx_and_logs(self, client):
        meta = _metadata()
        with patch("src.api.resume_generator.resume_ai_service.tailor",
                   new_callable=AsyncMock, return_value=_tailored()), \
             patch("src.api.resume_generator.resume_generator_service.generate_and_log",
                   new_callable=AsyncMock,
                   return_value=(_docx_stream(), "resume.docx", meta)), \
             patch("src.api.resume_generator.generation_audit_service.attach_application",
                   new_callable=AsyncMock) as attach:
            resp = await client.post("/api/v1/generate-resume-from-jd", json=_jd_body())
        assert resp.status_code == 200
        assert resp.headers["x-application-id"] == meta.application_id
        # The audit row is linked to the produced application.
        attach.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_error_returns_502_with_correlation_id(self, client):
        with patch("src.api.resume_generator.resume_ai_service.tailor",
                   new_callable=AsyncMock, side_effect=LLMError("upstream 500")):
            resp = await client.post("/api/v1/generate-resume-from-jd", json=_jd_body())
        assert resp.status_code == 502
        assert "x-correlation-id" in resp.headers

    @pytest.mark.asyncio
    async def test_validation_error_returns_422(self, client):
        # Model produced JSON that failed ResumeRequest validation.
        with patch("src.api.resume_generator.resume_ai_service.tailor",
                   new_callable=AsyncMock,
                   side_effect=ValidationError("bad schema from model")):
            resp = await client.post("/api/v1/generate-resume-from-jd", json=_jd_body())
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_no_base_resume_returns_404(self, client):
        with patch("src.api.resume_generator.resume_ai_service.tailor",
                   new_callable=AsyncMock,
                   side_effect=NotFoundError("base_resume", "owner")):
            resp = await client.post("/api/v1/generate-resume-from-jd", json=_jd_body())
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_too_short_jd_returns_422(self, client):
        # min_length=20 on job_description
        resp = await client.post("/api/v1/generate-resume-from-jd",
                                 json=_jd_body(job_description="too short"))
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_oversized_jd_returns_422(self, client):
        # max_length=20_000 on job_description (TD-7)
        resp = await client.post("/api/v1/generate-resume-from-jd",
                                 json=_jd_body(job_description="x" * 20_001))
        assert resp.status_code == 422
