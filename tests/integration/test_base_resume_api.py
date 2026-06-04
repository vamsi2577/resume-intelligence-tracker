"""
Integration tests for the base / master résumé API routes.

Service layer is mocked — no live DB required.

Run:  pytest tests/integration/test_base_resume_api.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.utils.exceptions import NotFoundError


def _row(**over) -> SimpleNamespace:
    base = dict(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        raw_text="Jane Doe — Senior Engineer. 10y experience.",
        structured_json=None,
        updated_at=datetime.now(timezone.utc),
    )
    base.update(over)
    return SimpleNamespace(**base)


# ── GET /api/v1/base-resume ───────────────────────────────

class TestGetBaseResume:
    @pytest.mark.asyncio
    async def test_returns_200(self, client):
        with patch("src.api.base_resume.base_resume_service.get_required",
                   new_callable=AsyncMock, return_value=_row()):
            resp = await client.get("/api/v1/base-resume")
        assert resp.status_code == 200
        assert resp.json()["raw_text"].startswith("Jane Doe")

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, client):
        with patch("src.api.base_resume.base_resume_service.get_required",
                   new_callable=AsyncMock,
                   side_effect=NotFoundError("base_resume", "owner")):
            resp = await client.get("/api/v1/base-resume")
        assert resp.status_code == 404


# ── PUT /api/v1/base-resume ───────────────────────────────

class TestPutBaseResume:
    @pytest.mark.asyncio
    async def test_upsert_returns_200(self, client):
        with patch("src.api.base_resume.base_resume_service.upsert",
                   new_callable=AsyncMock, return_value=_row()) as svc:
            resp = await client.put("/api/v1/base-resume",
                                    json={"raw_text": "New résumé text"})
        assert resp.status_code == 200
        svc.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_accepts_structured_json(self, client):
        row = _row(structured_json={"skills": ["python"]})
        with patch("src.api.base_resume.base_resume_service.upsert",
                   new_callable=AsyncMock, return_value=row):
            resp = await client.put(
                "/api/v1/base-resume",
                json={"raw_text": "text", "structured_json": {"skills": ["python"]}},
            )
        assert resp.status_code == 200
        assert resp.json()["structured_json"] == {"skills": ["python"]}

    @pytest.mark.asyncio
    async def test_missing_raw_text_returns_422(self, client):
        resp = await client.put("/api/v1/base-resume", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_raw_text_returns_422(self, client):
        # min_length=1 on raw_text
        resp = await client.put("/api/v1/base-resume", json={"raw_text": ""})
        assert resp.status_code == 422
