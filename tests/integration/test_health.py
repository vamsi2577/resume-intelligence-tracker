"""
Integration tests for GET /health endpoint.

Requires a running PostgreSQL container:
    docker-compose up -d

Run:  pytest tests/integration/test_health.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch


# ── Live DB tests (requires docker-compose up) ────────────

class TestHealthLive:
    @pytest.mark.asyncio
    async def test_returns_200_when_db_up(self, client):
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_response_has_required_fields(self, client):
        data = (await client.get("/health")).json()
        for field in ("status", "db", "env", "correlation_id"):
            assert field in data

    @pytest.mark.asyncio
    async def test_status_healthy_when_db_up(self, client):
        data = (await client.get("/health")).json()
        assert data["status"] == "healthy"
        assert data["db"] == "ok"

    @pytest.mark.asyncio
    async def test_correlation_id_in_response_header(self, client):
        response = await client.get("/health")
        assert "x-correlation-id" in response.headers

    @pytest.mark.asyncio
    async def test_correlation_id_matches_body(self, client):
        response = await client.get("/health")
        assert response.json()["correlation_id"] == response.headers["x-correlation-id"]


# ── Mocked DB-down tests ──────────────────────────────────

class TestHealthDegraded:
    @pytest.mark.asyncio
    async def test_returns_503_when_db_unreachable(self, client):
        with patch("src.api.health._check_db", new_callable=AsyncMock, return_value="unreachable"):
            response = await client.get("/health")
        assert response.status_code == 503
        assert response.json()["status"] == "degraded"
        assert response.json()["db"] == "unreachable"

    @pytest.mark.asyncio
    async def test_returns_503_on_db_timeout(self, client):
        with patch("src.api.health._check_db", new_callable=AsyncMock, return_value="timeout"):
            response = await client.get("/health")
        assert response.status_code == 503
        assert response.json()["db"] == "timeout"

    @pytest.mark.asyncio
    async def test_degraded_still_returns_correlation_id(self, client):
        with patch("src.api.health._check_db", new_callable=AsyncMock, return_value="unreachable"):
            response = await client.get("/health")
        assert "x-correlation-id" in response.headers
