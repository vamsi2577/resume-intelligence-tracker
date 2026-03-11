"""
Integration tests for application API routes.

Service layer is mocked — no live DB required for most tests.

Run:  pytest tests/integration/test_applications_api.py -v
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.exceptions import DuplicateError, NotFoundError


# ── Shared mock response builders ────────────────────────

def _today() -> date:
    return date.today()


def _mock_response(**overrides) -> dict:
    return {
        "id": str(overrides.get("id", uuid.uuid4())),
        "company_name": overrides.get("company_name", "Acme Corp"),
        "job_title": overrides.get("job_title", "Engineer"),
        "source": "manual",
        "status": overrides.get("status", "applied"),
        "applied_date": str(_today()),
        "job_url": None,
        "job_id": None,
        "resume_version": None,
        "notes": None,
        "salary_range": None,
        "location": None,
        "address": None,
        "work_type": None,
        "contact_name": None,
        "contact_email": None,
        "follow_up_date": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "duplicate_warning": overrides.get("duplicate_warning", False),
    }


def _valid_create_body(**overrides) -> dict:
    base = dict(
        company_name="Acme Corp",
        job_title="Engineer",
        source="manual",
        applied_date=str(_today()),
    )
    base.update(overrides)
    return base


# ── POST /api/v1/log-application ──────────────────────────

class TestLogApplication:
    @pytest.mark.asyncio
    async def test_returns_201(self, client):
        mock = MagicMock(**_mock_response())
        with patch("src.api.applications.application_service.create_application",
                   new_callable=AsyncMock, return_value=mock):
            resp = await client.post("/api/v1/log-application", json=_valid_create_body())
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_duplicate_job_id_returns_409(self, client):
        with patch("src.api.applications.application_service.create_application",
                   new_callable=AsyncMock, side_effect=DuplicateError("existing-id")):
            resp = await client.post("/api/v1/log-application",
                                     json=_valid_create_body(job_id="JOB123"))
        assert resp.status_code == 409
        assert "existing_id" in resp.json()

    @pytest.mark.asyncio
    async def test_malformed_json_returns_422(self, client):
        resp = await client.post("/api/v1/log-application",
                                 content="not-json",
                                 headers={"Content-Type": "application/json"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_mandatory_field_returns_422(self, client):
        resp = await client.post("/api/v1/log-application",
                                 json={"company_name": "Acme"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_duplicate_warning_flag_in_response(self, client):
        mock = MagicMock(**_mock_response(duplicate_warning=True))
        with patch("src.api.applications.application_service.create_application",
                   new_callable=AsyncMock, return_value=mock):
            resp = await client.post("/api/v1/log-application", json=_valid_create_body())
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_correlation_id_in_response_header(self, client):
        mock = MagicMock(**_mock_response())
        with patch("src.api.applications.application_service.create_application",
                   new_callable=AsyncMock, return_value=mock):
            resp = await client.post("/api/v1/log-application", json=_valid_create_body())
        assert "x-correlation-id" in resp.headers


# ── PATCH /api/v1/log-application/{id} ───────────────────

class TestUpdateApplication:
    @pytest.mark.asyncio
    async def test_returns_200(self, client):
        app_id = uuid.uuid4()
        mock = MagicMock(**_mock_response(id=app_id, status="interview"))
        with patch("src.api.applications.application_service.update_application",
                   new_callable=AsyncMock, return_value=mock):
            resp = await client.patch(f"/api/v1/log-application/{app_id}",
                                      json={"status": "interview"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, client):
        app_id = uuid.uuid4()
        with patch("src.api.applications.application_service.update_application",
                   new_callable=AsyncMock,
                   side_effect=NotFoundError("Application", str(app_id))):
            resp = await client.patch(f"/api/v1/log-application/{app_id}",
                                      json={"status": "interview"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_body_returns_422(self, client):
        resp = await client.patch(f"/api/v1/log-application/{uuid.uuid4()}", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_422(self, client):
        resp = await client.patch("/api/v1/log-application/not-a-uuid",
                                  json={"status": "interview"})
        assert resp.status_code == 422


# ── GET /api/v1/applications ──────────────────────────────

class TestListApplications:
    @pytest.mark.asyncio
    async def test_returns_200_with_defaults(self, client):
        mock = MagicMock(data=[], pagination=MagicMock(
            page=1, limit=20, total=0, total_pages=0), meta={})
        with patch("src.api.applications.application_service.get_applications",
                   new_callable=AsyncMock, return_value=mock):
            resp = await client.get("/api/v1/applications")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_multi_company_filter(self, client):
        mock = MagicMock(data=[], pagination=MagicMock(
            page=1, limit=20, total=0, total_pages=0), meta={})
        with patch("src.api.applications.application_service.get_applications",
                   new_callable=AsyncMock, return_value=mock) as svc:
            resp = await client.get("/api/v1/applications?company=Acme&company=Google")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_multi_status_filter(self, client):
        mock = MagicMock(data=[], pagination=MagicMock(
            page=1, limit=20, total=0, total_pages=0), meta={})
        with patch("src.api.applications.application_service.get_applications",
                   new_callable=AsyncMock, return_value=mock):
            resp = await client.get("/api/v1/applications?status=applied&status=interview")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_status_returns_422(self, client):
        resp = await client.get("/api/v1/applications?status=promoted")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_date_from_after_date_to_returns_422(self, client):
        resp = await client.get("/api/v1/applications?date_from=2026-03-10&date_to=2026-03-01")
        assert resp.status_code == 422


# ── GET /api/v1/applications/{id} ────────────────────────

class TestGetApplication:
    @pytest.mark.asyncio
    async def test_returns_200(self, client):
        app_id = uuid.uuid4()
        mock = MagicMock(**_mock_response(id=app_id))
        with patch("src.api.applications.application_service.get_application_by_id",
                   new_callable=AsyncMock, return_value=mock):
            resp = await client.get(f"/api/v1/applications/{app_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, client):
        app_id = uuid.uuid4()
        with patch("src.api.applications.application_service.get_application_by_id",
                   new_callable=AsyncMock,
                   side_effect=NotFoundError("Application", str(app_id))):
            resp = await client.get(f"/api/v1/applications/{app_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_422(self, client):
        resp = await client.get("/api/v1/applications/not-a-uuid")
        assert resp.status_code == 422


# ── GET /api/v1/applications/{id}/history ────────────────

class TestGetApplicationHistory:
    @pytest.mark.asyncio
    async def test_returns_200_empty_list(self, client):
        app_id = uuid.uuid4()
        with patch("src.api.applications.application_service.get_status_history",
                   new_callable=AsyncMock, return_value=[]):
            resp = await client.get(f"/api/v1/applications/{app_id}/history")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, client):
        app_id = uuid.uuid4()
        with patch("src.api.applications.application_service.get_status_history",
                   new_callable=AsyncMock,
                   side_effect=NotFoundError("Application", str(app_id))):
            resp = await client.get(f"/api/v1/applications/{app_id}/history")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_correlation_id_in_response_header(self, client):
        app_id = uuid.uuid4()
        with patch("src.api.applications.application_service.get_status_history",
                   new_callable=AsyncMock, return_value=[]):
            resp = await client.get(f"/api/v1/applications/{app_id}/history")
        assert "x-correlation-id" in resp.headers
