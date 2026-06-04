"""
Integration tests for the generation-history (observability) API route.

  GET /api/v1/generation-history

Service layer is mocked — no live DB required.

Run:  pytest tests/integration/test_generation_history_api.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.schemas.resume_generation import GenerationStatsResponse


def _gen_row(**over) -> SimpleNamespace:
    base = dict(
        id=uuid.uuid4(),
        correlation_id="corr-123",
        status="success",
        target_company="Acme",
        job_title="Engineer",
        jd_chars=500,
        preview=False,
        provider="groq",
        model="llama-3.3-70b",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        duration_ms=1200,
        application_id=uuid.uuid4(),
        error_message=None,
        created_at=datetime.now(timezone.utc),
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestGenerationHistory:
    @pytest.mark.asyncio
    async def test_returns_200_with_data_and_stats(self, client):
        stats = GenerationStatsResponse(
            total=3, success=2, llm_error=1, validation_error=0,
            success_rate=0.667, avg_duration_ms=1100, total_tokens=450,
        )
        with patch("src.api.generation_history.generation_audit_service.list_recent",
                   new_callable=AsyncMock, return_value=[_gen_row(), _gen_row(status="llm_error")]), \
             patch("src.api.generation_history.generation_audit_service.get_stats",
                   new_callable=AsyncMock, return_value=stats):
            resp = await client.get("/api/v1/generation-history")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["stats"]["total"] == 3
        # llm_raw_output is intentionally excluded from the list view.
        assert "llm_raw_output" not in body["data"][0]

    @pytest.mark.asyncio
    async def test_empty_history_returns_200(self, client):
        with patch("src.api.generation_history.generation_audit_service.list_recent",
                   new_callable=AsyncMock, return_value=[]), \
             patch("src.api.generation_history.generation_audit_service.get_stats",
                   new_callable=AsyncMock, return_value=GenerationStatsResponse()):
            resp = await client.get("/api/v1/generation-history")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    @pytest.mark.asyncio
    async def test_limit_passed_to_service(self, client):
        with patch("src.api.generation_history.generation_audit_service.list_recent",
                   new_callable=AsyncMock, return_value=[]) as lst, \
             patch("src.api.generation_history.generation_audit_service.get_stats",
                   new_callable=AsyncMock, return_value=GenerationStatsResponse()):
            resp = await client.get("/api/v1/generation-history?limit=10")
        assert resp.status_code == 200
        assert lst.await_args.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_limit_below_min_returns_422(self, client):
        resp = await client.get("/api/v1/generation-history?limit=0")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_limit_above_max_returns_422(self, client):
        resp = await client.get("/api/v1/generation-history?limit=201")
        assert resp.status_code == 422
