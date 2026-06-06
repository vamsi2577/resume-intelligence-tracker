"""
Magic-link auth integration tests (Phase 2).

Covers request-link → verify → session cookie, auto-registration with the
default role, single-use + expiry enforcement, logout, and the REQUIRE_AUTH
toggle on get_current_owner.

Uses a per-test NullPool engine + get_db override (same pattern as the IAM /
tenant-isolation suites). Magic-link tokens are read back from the DB (dev
"email" is logged, not sent).

Run:  pytest tests/integration/test_auth_api.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.deps import get_current_owner
from src.core.config import settings
from src.db.session import get_db
from src.main import app
from src.services import auth_service


@pytest_asyncio.fixture
async def authdb():
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
    app.dependency_overrides.pop(get_current_owner, None)
    # Clean up any users/tokens created by the tests.
    async with factory() as s:
        await s.execute(text("DELETE FROM users WHERE email LIKE '%@magic-auth.io'"))
        await s.execute(text("DELETE FROM login_tokens WHERE email LIKE '%@magic-auth.io'"))
        await s.commit()
    await engine.dispose()


async def _raw_token_for(factory, email: str) -> str:
    """Issue a token directly via the service so the test knows the raw value
    (the API only emails it)."""
    async with factory() as s:
        raw = await auth_service.request_login(s, email)
        await s.commit()
    return raw


# ── request-link ──────────────────────────────────────────

class TestRequestLink:
    @pytest.mark.asyncio
    async def test_returns_generic_ok_and_stores_hash(self, client, authdb):
        email = f"{uuid.uuid4()}@magic-auth.io"
        resp = await client.post("/api/v1/auth/request-link", json={"email": email})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # A hashed token row exists; the raw token is never stored.
        async with authdb() as s:
            row = (await s.execute(text(
                "SELECT token_hash FROM login_tokens WHERE email = :e"
            ).bindparams(e=email))).scalar_one_or_none()
        assert row is not None and len(row) == 64

    @pytest.mark.asyncio
    async def test_invalid_email_422(self, client, authdb):
        resp = await client.post("/api/v1/auth/request-link", json={"email": "not-an-email"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_purges_stale_tokens_for_email(self, client, authdb):
        email = f"{uuid.uuid4()}@magic-auth.io"
        # Seed one consumed and one expired token for this email.
        async with authdb() as s:
            from src.models.login_token import LoginToken

            s.add(LoginToken(
                id=uuid.uuid4(), email=email, token_hash="a" * 64,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                consumed_at=datetime.now(timezone.utc),
            ))
            s.add(LoginToken(
                id=uuid.uuid4(), email=email, token_hash="b" * 64,
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            ))
            await s.commit()

        resp = await client.post("/api/v1/auth/request-link", json={"email": email})
        assert resp.status_code == 200

        # Stale rows purged; exactly one fresh, unconsumed, unexpired token left.
        async with authdb() as s:
            rows = (await s.execute(text(
                "SELECT consumed_at, expires_at FROM login_tokens WHERE email = :e"
            ).bindparams(e=email))).all()
        assert len(rows) == 1
        assert rows[0][0] is None  # not consumed
        assert rows[0][1] > datetime.now(timezone.utc)  # not expired


# ── verify ────────────────────────────────────────────────

class TestVerify:
    @pytest.mark.asyncio
    async def test_verify_sets_cookie_and_autoregisters(self, client, authdb):
        email = f"{uuid.uuid4()}@magic-auth.io"
        raw = await _raw_token_for(authdb, email)

        resp = await client.get(f"/api/v1/auth/verify?token={raw}&email={email}")
        assert resp.status_code == 200
        assert resp.json()["email"] == email
        assert settings.SESSION_COOKIE_NAME in resp.cookies

        # User was created and granted the default `user` role.
        async with authdb() as s:
            roles = (await s.execute(text(
                "SELECT r.name FROM users u "
                "JOIN user_roles ur ON ur.user_id = u.id "
                "JOIN roles r ON r.id = ur.role_id WHERE u.email = :e"
            ).bindparams(e=email))).all()
        assert ["user"] == [r[0] for r in roles]

    @pytest.mark.asyncio
    async def test_token_is_single_use(self, client, authdb):
        email = f"{uuid.uuid4()}@magic-auth.io"
        raw = await _raw_token_for(authdb, email)
        assert (await client.get(f"/api/v1/auth/verify?token={raw}&email={email}")).status_code == 200
        # Second use → 401.
        resp = await client.get(f"/api/v1/auth/verify?token={raw}&email={email}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_token_401(self, client, authdb):
        email = f"{uuid.uuid4()}@magic-auth.io"
        await _raw_token_for(authdb, email)
        resp = await client.get(f"/api/v1/auth/verify?token={'x' * 40}&email={email}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_401(self, client, authdb):
        email = f"{uuid.uuid4()}@magic-auth.io"
        raw = await _raw_token_for(authdb, email)
        # Force-expire the token.
        async with authdb() as s:
            await s.execute(text(
                "UPDATE login_tokens SET expires_at = :t WHERE email = :e"
            ).bindparams(t=datetime.now(timezone.utc) - timedelta(minutes=1), e=email))
            await s.commit()
        resp = await client.get(f"/api/v1/auth/verify?token={raw}&email={email}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_deactivated_user_cannot_verify(self, client, authdb):
        # Register, then deactivate the account; a fresh valid link must 401.
        email = f"{uuid.uuid4()}@magic-auth.io"
        raw1 = await _raw_token_for(authdb, email)
        assert (await client.get(f"/api/v1/auth/verify?token={raw1}&email={email}")).status_code == 200
        async with authdb() as s:
            await s.execute(text(
                "UPDATE users SET is_active = false WHERE email = :e"
            ).bindparams(e=email))
            await s.commit()
        raw2 = await _raw_token_for(authdb, email)
        resp = await client.get(f"/api/v1/auth/verify?token={raw2}&email={email}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_existing_user_reused(self, client, authdb):
        email = f"{uuid.uuid4()}@magic-auth.io"
        raw1 = await _raw_token_for(authdb, email)
        uid1 = (await client.get(f"/api/v1/auth/verify?token={raw1}&email={email}")).json()["user_id"]
        raw2 = await _raw_token_for(authdb, email)
        uid2 = (await client.get(f"/api/v1/auth/verify?token={raw2}&email={email}")).json()["user_id"]
        assert uid1 == uid2  # same account, not a duplicate


# ── session JWT + REQUIRE_AUTH toggle ─────────────────────

class TestSession:
    def test_issue_and_decode_roundtrip(self):
        uid = uuid.uuid4()
        token = auth_service.issue_session(uid, 3)
        claims = auth_service.decode_session(token)
        assert claims.user_id == uid
        assert claims.token_version == 3

    def test_decode_defaults_tv_to_zero_for_legacy_tokens(self):
        # A token issued without an explicit tv reads back as 0 (non-breaking).
        token = auth_service.issue_session(uuid.uuid4())
        assert auth_service.decode_session(token).token_version == 0

    def test_decode_garbage_raises(self):
        from src.utils.exceptions import UnauthorizedError
        with pytest.raises(UnauthorizedError):
            auth_service.decode_session("not.a.jwt")

    def test_decode_falls_back_to_previous_secret_during_rotation(self, monkeypatch):
        from pydantic import SecretStr
        uid = uuid.uuid4()
        # Token signed under the old secret.
        monkeypatch.setattr(settings, "JWT_SECRET", SecretStr("old-secret"))
        token = auth_service.issue_session(uid, 0)
        # Rotate: new secret current, old secret retained for verify.
        monkeypatch.setattr(settings, "JWT_SECRET", SecretStr("new-secret"))
        monkeypatch.setattr(settings, "JWT_SECRET_PREVIOUS", SecretStr("old-secret"))
        assert auth_service.decode_session(token).user_id == uid

    def test_decode_rejects_token_signed_with_unknown_secret(self, monkeypatch):
        from pydantic import SecretStr
        from src.utils.exceptions import UnauthorizedError
        monkeypatch.setattr(settings, "JWT_SECRET", SecretStr("secret-A"))
        token = auth_service.issue_session(uuid.uuid4(), 0)
        # New current secret, no previous → the old token no longer verifies.
        monkeypatch.setattr(settings, "JWT_SECRET", SecretStr("secret-B"))
        monkeypatch.setattr(settings, "JWT_SECRET_PREVIOUS", SecretStr(""))
        with pytest.raises(UnauthorizedError):
            auth_service.decode_session(token)

    @pytest.mark.asyncio
    async def test_require_auth_off_uses_default_owner(self, client, authdb):
        # Default config: REQUIRE_AUTH off → /auth/me works with no cookie.
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["user_id"] == settings.DEFAULT_OWNER_ID

    @pytest.mark.asyncio
    async def test_require_auth_on_blocks_without_cookie(self, client, authdb, monkeypatch):
        monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_require_auth_on_accepts_valid_cookie(self, client, authdb, monkeypatch):
        email = f"{uuid.uuid4()}@magic-auth.io"
        raw = await _raw_token_for(authdb, email)
        verify = await client.get(f"/api/v1/auth/verify?token={raw}&email={email}")
        uid = verify.json()["user_id"]
        cookie = verify.cookies[settings.SESSION_COOKIE_NAME]

        monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
        resp = await client.get(
            "/api/v1/auth/me",
            cookies={settings.SESSION_COOKIE_NAME: cookie},
        )
        assert resp.status_code == 200
        assert resp.json()["user_id"] == uid

    @pytest.mark.asyncio
    async def test_require_auth_on_rejects_deactivated_user(self, client, authdb, monkeypatch):
        # A valid cookie for a now-deactivated account must be rejected (401),
        # not honored until the JWT expires.
        email = f"{uuid.uuid4()}@magic-auth.io"
        raw = await _raw_token_for(authdb, email)
        verify = await client.get(f"/api/v1/auth/verify?token={raw}&email={email}")
        cookie = verify.cookies[settings.SESSION_COOKIE_NAME]

        async with authdb() as s:
            await s.execute(text(
                "UPDATE users SET is_active = false WHERE email = :e"
            ).bindparams(e=email))
            await s.commit()

        monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
        resp = await client.get(
            "/api/v1/auth/me",
            cookies={settings.SESSION_COOKIE_NAME: cookie},
        )
        assert resp.status_code == 401


# ── login-token sweep ─────────────────────────────────────

class TestSweep:
    @pytest.mark.asyncio
    async def test_purge_removes_consumed_and_expired_keeps_live(self, authdb):
        from src.models.login_token import LoginToken
        email = f"{uuid.uuid4()}@magic-auth.io"
        now = datetime.now(timezone.utc)
        async with authdb() as s:
            s.add(LoginToken(id=uuid.uuid4(), email=email, token_hash="c" * 64,
                             expires_at=now + timedelta(minutes=15), consumed_at=now))  # consumed
            s.add(LoginToken(id=uuid.uuid4(), email=email, token_hash="e" * 64,
                             expires_at=now - timedelta(minutes=1)))                    # expired
            s.add(LoginToken(id=uuid.uuid4(), email=email, token_hash="l" * 64,
                             expires_at=now + timedelta(minutes=15)))                   # live
            await s.commit()

        async with authdb() as s:
            removed = await auth_service.purge_expired_login_tokens(s)
            await s.commit()
        assert removed >= 2  # at least our consumed + expired (global sweep)

        async with authdb() as s:
            rows = (await s.execute(text(
                "SELECT token_hash FROM login_tokens WHERE email = :e"
            ).bindparams(e=email))).all()
        assert [r[0] for r in rows] == ["l" * 64]  # only the live token survives


# ── logout ────────────────────────────────────────────────

class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_clears_cookie(self, client, authdb):
        resp = await client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        # Set-Cookie with an expiry in the past / empty value.
        assert settings.SESSION_COOKIE_NAME in resp.headers.get("set-cookie", "")

    @pytest.mark.asyncio
    async def test_logout_all_revokes_existing_sessions(self, client, authdb, monkeypatch):
        # Sign in, then "log out everywhere" → the same cookie is dead afterward
        # (token_version bumped past the token's tv).
        email = f"{uuid.uuid4()}@magic-auth.io"
        raw = await _raw_token_for(authdb, email)
        verify = await client.get(f"/api/v1/auth/verify?token={raw}&email={email}")
        cookie = verify.cookies[settings.SESSION_COOKIE_NAME]

        monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
        hdr = {settings.SESSION_COOKIE_NAME: cookie}

        assert (await client.get("/api/v1/auth/me", cookies=hdr)).status_code == 200
        assert (await client.post("/api/v1/auth/logout-all", cookies=hdr)).status_code == 200
        # Same cookie now rejected — its tv no longer matches the user's.
        assert (await client.get("/api/v1/auth/me", cookies=hdr)).status_code == 401
