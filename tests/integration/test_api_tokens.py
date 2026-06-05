"""
Personal API token integration tests (Phase 2).

Covers: token creation (raw shown once, hash at rest), listing without the
secret, owner-scoped revocation, and the Bearer path in get_current_owner
(resolves to the token's owner, overrides the default owner, and rejects
revoked / expired / inactive-owner / malformed credentials).

Uses the per-test NullPool engine + get_db override pattern. Test users use the
`@api-token.io` domain so cleanup is targeted.

Run:  pytest tests/integration/test_api_tokens.py -v
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
from src.models.user import User
from src.services import token_service

DEFAULT_OWNER = settings.DEFAULT_OWNER_ID


@pytest_asyncio.fixture
async def tokdb():
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
    async with factory() as s:
        await s.execute(text(
            "DELETE FROM api_tokens WHERE owner_id = CAST(:d AS uuid) "
            "OR owner_id IN (SELECT id FROM users WHERE email LIKE '%@api-token.io')"
        ).bindparams(d=DEFAULT_OWNER))
        await s.execute(text("DELETE FROM users WHERE email LIKE '%@api-token.io'"))
        await s.commit()
    await engine.dispose()


async def _make_user(factory, *, active: bool = True) -> uuid.UUID:
    uid = uuid.uuid4()
    async with factory() as s:
        s.add(User(id=uid, email=f"{uid}@api-token.io", is_active=active))
        await s.commit()
    return uid


async def _mint(factory, owner_id: uuid.UUID, **kw) -> str:
    async with factory() as s:
        _, raw = await token_service.create_token(s, owner_id, kw.pop("name", "test"), **kw)
        await s.commit()
    return raw


def _bearer(raw: str) -> dict:
    return {"Authorization": f"Bearer {raw}"}


# ── creation / listing ────────────────────────────────────

class TestCreateList:
    @pytest.mark.asyncio
    async def test_create_returns_raw_and_stores_hash(self, client, tokdb):
        resp = await client.post("/api/v1/auth/tokens", json={"name": "my laptop"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["token"].startswith("rit_")
        assert body["name"] == "my laptop"
        assert body["token"].startswith(body["token_prefix"])

        # The raw token is not stored — only its hash.
        async with tokdb() as s:
            stored = (await s.execute(text(
                "SELECT token_hash FROM api_tokens WHERE id = CAST(:i AS uuid)"
            ).bindparams(i=body["id"]))).scalar_one()
        assert stored != body["token"] and len(stored) == 64

    @pytest.mark.asyncio
    async def test_create_with_expiry(self, client, tokdb):
        resp = await client.post(
            "/api/v1/auth/tokens", json={"name": "temp", "expires_in_days": 7}
        )
        assert resp.status_code == 201
        assert resp.json()["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_create_requires_name(self, client, tokdb):
        resp = await client.post("/api/v1/auth/tokens", json={"name": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_omits_secret(self, client, tokdb):
        await client.post("/api/v1/auth/tokens", json={"name": "one"})
        resp = await client.get("/api/v1/auth/tokens")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) >= 1
        assert all("token" not in r for r in rows)
        assert all("token_prefix" in r for r in rows)


# ── bearer auth on get_current_owner ──────────────────────

class TestBearerAuth:
    @pytest.mark.asyncio
    async def test_bearer_resolves_to_token_owner(self, client, tokdb):
        # A token for a specific user wins over the default owner.
        uid = await _make_user(tokdb)
        raw = await _mint(tokdb, uid)
        resp = await client.get("/api/v1/auth/me", headers=_bearer(raw))
        assert resp.status_code == 200
        assert resp.json()["user_id"] == str(uid)
        assert resp.json()["user_id"] != DEFAULT_OWNER

    @pytest.mark.asyncio
    async def test_revoked_token_rejected(self, client, tokdb):
        uid = await _make_user(tokdb)
        async with tokdb() as s:
            tok, raw = await token_service.create_token(s, uid, "to-revoke")
            tok.revoked_at = datetime.now(timezone.utc)
            await s.commit()
        resp = await client.get("/api/v1/auth/me", headers=_bearer(raw))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, client, tokdb):
        uid = await _make_user(tokdb)
        raw = await _mint(tokdb, uid, expires_in_days=1)
        async with tokdb() as s:
            await s.execute(text(
                "UPDATE api_tokens SET expires_at = :t WHERE owner_id = CAST(:o AS uuid)"
            ).bindparams(t=datetime.now(timezone.utc) - timedelta(days=1), o=str(uid)))
            await s.commit()
        resp = await client.get("/api/v1/auth/me", headers=_bearer(raw))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_owner_token_rejected(self, client, tokdb):
        uid = await _make_user(tokdb, active=False)
        raw = await _mint(tokdb, uid)
        resp = await client.get("/api/v1/auth/me", headers=_bearer(raw))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_token_rejected(self, client, tokdb):
        resp = await client.get("/api/v1/auth/me", headers=_bearer("rit_does-not-exist"))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_authorization_header_rejected(self, client, tokdb):
        resp = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Basic abc123"}
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_last_used_at_stamped(self, client, tokdb):
        uid = await _make_user(tokdb)
        raw = await _mint(tokdb, uid)
        await client.get("/api/v1/auth/me", headers=_bearer(raw))
        async with tokdb() as s:
            used = (await s.execute(text(
                "SELECT last_used_at FROM api_tokens WHERE owner_id = CAST(:o AS uuid)"
            ).bindparams(o=str(uid)))).scalar_one()
        assert used is not None


# ── revocation (owner scoping) ────────────────────────────

class TestRevoke:
    @pytest.mark.asyncio
    async def test_owner_can_revoke_own_token(self, client, tokdb):
        created = (await client.post("/api/v1/auth/tokens", json={"name": "x"})).json()
        resp = await client.delete(f"/api/v1/auth/tokens/{created['id']}")
        assert resp.status_code == 204
        # Revoked tokens still list (with revoked_at set) but can't authenticate.
        async with tokdb() as s:
            revoked = (await s.execute(text(
                "SELECT revoked_at FROM api_tokens WHERE id = CAST(:i AS uuid)"
            ).bindparams(i=created["id"]))).scalar_one()
        assert revoked is not None

    @pytest.mark.asyncio
    async def test_cannot_revoke_another_users_token(self, client, tokdb):
        # A token owned by a different user → 404 (no existence leak), since the
        # caller here is the default owner.
        other = await _make_user(tokdb)
        async with tokdb() as s:
            tok, _ = await token_service.create_token(s, other, "theirs")
            await s.commit()
            other_token_id = tok.id
        resp = await client.delete(f"/api/v1/auth/tokens/{other_token_id}")
        assert resp.status_code == 404
