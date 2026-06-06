"""
Auth endpoint rate limiting (Phase 5 auth-hardening PR2).

Verifies request-link is throttled per-IP and per-email and verify is throttled
per-IP, returning 429 + Retry-After. Rate limiting is disabled globally for the
suite (see conftest `_disable_rate_limiting`); these tests opt back in and reset
the shared limiter so counts are deterministic.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.db.session import get_db
from src.main import app
from src.utils.ratelimit import auth_limiter


@pytest_asyncio.fixture
async def rldb():
    """Per-test NullPool engine + get_db override (same pattern as the other
    auth suites) — the app's module-level engine breaks under pytest-asyncio's
    per-test event loops."""
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    yield factory
    app.dependency_overrides.pop(get_db, None)
    async with factory() as s:
        await s.execute(text("DELETE FROM login_tokens WHERE email LIKE '%@magic-auth.io'"))
        await s.commit()
    await engine.dispose()


@pytest.fixture
def rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "AUTH_RL_IP_PER_MINUTE", 3)
    monkeypatch.setattr(settings, "AUTH_RL_EMAIL_PER_HOUR", 2)
    auth_limiter.reset()
    yield
    auth_limiter.reset()


async def _post_link(client, email):
    return await client.post("/api/v1/auth/request-link", json={"email": email})


class TestRequestLinkLimits:
    @pytest.mark.asyncio
    async def test_per_email_limit_returns_429(self, client, rldb, rate_limited):
        email = f"{uuid.uuid4()}@magic-auth.io"
        # Limit is 2/hour for one email.
        assert (await _post_link(client, email)).status_code == 200
        assert (await _post_link(client, email)).status_code == 200
        resp = await _post_link(client, email)
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") is not None

    @pytest.mark.asyncio
    async def test_per_ip_limit_returns_429_across_emails(self, client, rldb, rate_limited):
        # IP limit is 3/min; use distinct emails so the per-email cap (2) isn't
        # what trips first.
        for _ in range(3):
            assert (await _post_link(client, f"{uuid.uuid4()}@magic-auth.io")).status_code == 200
        resp = await _post_link(client, f"{uuid.uuid4()}@magic-auth.io")
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_disabled_flag_means_no_limit(self, client, rldb, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        auth_limiter.reset()
        email = f"{uuid.uuid4()}@magic-auth.io"
        for _ in range(6):
            assert (await _post_link(client, email)).status_code == 200


class TestVerifyLimits:
    @pytest.mark.asyncio
    async def test_verify_per_ip_limit_returns_429(self, client, rldb, rate_limited):
        # IP limit 3/min; verify with a bogus token still counts toward the limit.
        # First 3 are 401 (bad token), the 4th is 429 (throttled).
        for _ in range(3):
            r = await client.get("/api/v1/auth/verify?token=" + ("x" * 20) + "&email=a@b.io")
            assert r.status_code == 401
        r = await client.get("/api/v1/auth/verify?token=" + ("x" * 20) + "&email=a@b.io")
        assert r.status_code == 429
