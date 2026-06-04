"""
Integration tests for the application lifecycle routes added in Phase 2:

  DELETE /api/v1/applications/{id}          — soft delete
  GET    /api/v1/applications/{id}/resume   — re-render stored résumé as DOCX

Service layer is mocked — no live DB required.

Run:  pytest tests/integration/test_application_lifecycle_api.py -v
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.exceptions import NotFoundError


def _mock_response(**overrides) -> dict:
    return {
        "id": str(overrides.get("id", uuid.uuid4())),
        "company_name": "Acme Corp",
        "job_title": "Engineer",
        "source": "resume_generator",
        "status": overrides.get("status", "applied"),
        "applied_date": str(date.today()),
        "job_url": None,
        "job_id": None,
        "job_description": None,
        "resume_version": None,
        "resume_content": None,
        "notes": None,
        "salary_range": None,
        "location": None,
        "address": None,
        "work_type": None,
        "contact_name": None,
        "contact_email": None,
        "follow_up_date": None,
        "needs_review": False,
        "is_deleted": overrides.get("is_deleted", True),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "duplicate_warning": False,
    }


# Minimal valid ResumeRequest JSON for re-rendering a DOCX.
_RESUME_CONTENT = {
    "target_company": "Acme Corp",
    "job_title": "Engineer",
    "full_name": "Jane Doe",
    "contact_info": "jane@example.com",
    "summary": {"summary_text": "Experienced engineer.", "summary_points": []},
    "experience": [
        {"title": "Engineer", "company": "Globex", "date": "2020–2024",
         "bullets": ["Built things."]}
    ],
}


# ── DELETE /api/v1/applications/{id} ──────────────────────

class TestSoftDeleteApplication:
    @pytest.mark.asyncio
    async def test_returns_200(self, client):
        app_id = uuid.uuid4()
        mock = MagicMock(**_mock_response(id=app_id, is_deleted=True))
        with patch("src.api.applications.application_service.delete_application",
                   new_callable=AsyncMock, return_value=mock):
            resp = await client.delete(f"/api/v1/applications/{app_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, client):
        app_id = uuid.uuid4()
        with patch("src.api.applications.application_service.delete_application",
                   new_callable=AsyncMock,
                   side_effect=NotFoundError("Application", str(app_id))):
            resp = await client.delete(f"/api/v1/applications/{app_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_422(self, client):
        resp = await client.delete("/api/v1/applications/not-a-uuid")
        assert resp.status_code == 422


# ── GET /api/v1/applications/{id}/resume ──────────────────

class TestDownloadApplicationResume:
    @pytest.mark.asyncio
    async def test_returns_docx(self, client):
        app_id = uuid.uuid4()
        with patch("src.api.applications.application_service.get_resume_content",
                   new_callable=AsyncMock, return_value=_RESUME_CONTENT):
            resp = await client.get(f"/api/v1/applications/{app_id}/resume")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert "attachment" in resp.headers["content-disposition"]
        assert len(resp.content) > 0

    @pytest.mark.asyncio
    async def test_no_resume_content_returns_404(self, client):
        app_id = uuid.uuid4()
        with patch("src.api.applications.application_service.get_resume_content",
                   new_callable=AsyncMock,
                   side_effect=NotFoundError("ResumeContent", str(app_id))):
            resp = await client.get(f"/api/v1/applications/{app_id}/resume")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_422(self, client):
        resp = await client.get("/api/v1/applications/not-a-uuid/resume")
        assert resp.status_code == 422
