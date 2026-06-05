"""
Cross-tenant isolation tests (Phase 1 canary).

Seeds data as User A, then acts as User B and asserts B can never read, edit,
or delete A's rows — applications, base résumé, or generation history. A
foreign row resolves to 404 (never 403 — we don't leak existence).

These exercise the owner-scoping enforcement added in PR2 by overriding the
`get_current_owner` dependency per request to switch tenants. Requires a live
Postgres (same as the other integration tests).

Run:  pytest tests/integration/test_tenant_isolation.py -v
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool

from src.api.deps import get_current_owner
from src.core.config import settings
from src.db.session import get_db
from src.main import app


# ── Fixtures ──────────────────────────────────────────────

@pytest_asyncio.fixture
async def two_users():
    """Two distinct committed users + a per-test DB engine bound to the
    current event loop.

    The app's module-level engine is created once at import and breaks under
    pytest-asyncio's per-test loops ("Event loop is closed"). So we override
    `get_db` with a NullPool engine created inside this fixture (same pattern
    as conftest's `db`), and reuse it for seeding/cleanup. owner_id FKs are
    ON DELETE CASCADE, so deleting the users wipes everything seeded under them.
    """
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

    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as s:
        for uid in (a_id, b_id):
            await s.execute(
                text(
                    "INSERT INTO users (id, email, is_active, created_at, updated_at) "
                    "VALUES (:id, :email, true, now(), now())"
                ).bindparams(id=uid, email=f"{uid}@isolation.test")
            )
        await s.commit()

    yield a_id, b_id, factory

    async with factory() as s:
        await s.execute(
            text("DELETE FROM users WHERE id = ANY(:ids)").bindparams(ids=[a_id, b_id])
        )
        await s.commit()
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_owner, None)
    await engine.dispose()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_current_owner, None)


def _act_as(owner_id: uuid.UUID) -> None:
    """Make subsequent requests run as this tenant."""
    app.dependency_overrides[get_current_owner] = lambda: owner_id


def _app_body(**over) -> dict:
    base = dict(
        company_name="Acme Corp",
        job_title="Engineer",
        source="manual",
        applied_date="2026-06-01",
    )
    base.update(over)
    return base


async def _seed_application(client, owner_id: uuid.UUID, **over) -> str:
    """Create an application owned by `owner_id`; return its id."""
    _act_as(owner_id)
    resp = await client.post("/api/v1/log-application", json=_app_body(**over))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── Applications ──────────────────────────────────────────

class TestApplicationIsolation:
    @pytest.mark.asyncio
    async def test_get_foreign_application_404(self, client, two_users):
        a_id, b_id, factory = two_users
        app_id = await _seed_application(client, a_id)

        _act_as(b_id)
        resp = await client.get(f"/api/v1/applications/{app_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_foreign_application_404(self, client, two_users):
        a_id, b_id, factory = two_users
        app_id = await _seed_application(client, a_id)

        _act_as(b_id)
        resp = await client.patch(
            f"/api/v1/log-application/{app_id}", json={"status": "interview"}
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_foreign_application_404(self, client, two_users):
        a_id, b_id, factory = two_users
        app_id = await _seed_application(client, a_id)

        _act_as(b_id)
        resp = await client.delete(f"/api/v1/applications/{app_id}")
        assert resp.status_code == 404

        # And A's row is untouched — still present in A's default list, which
        # excludes soft-deleted rows (so its presence proves it wasn't deleted).
        _act_as(a_id)
        resp = await client.get("/api/v1/applications")
        assert resp.status_code == 200
        assert app_id in {row["id"] for row in resp.json()["data"]}

    @pytest.mark.asyncio
    async def test_list_only_returns_own(self, client, two_users):
        a_id, b_id, factory = two_users
        a_app = await _seed_application(client, a_id, company_name="A-Only Corp")
        b_app = await _seed_application(client, b_id, company_name="B-Only Corp")

        _act_as(b_id)
        resp = await client.get("/api/v1/applications")
        assert resp.status_code == 200
        ids = {row["id"] for row in resp.json()["data"]}
        assert b_app in ids
        assert a_app not in ids

    @pytest.mark.asyncio
    async def test_history_foreign_404(self, client, two_users):
        a_id, b_id, factory = two_users
        app_id = await _seed_application(client, a_id)

        _act_as(b_id)
        resp = await client.get(f"/api/v1/applications/{app_id}/history")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_download_foreign_404(self, client, two_users):
        a_id, b_id, factory = two_users
        app_id = await _seed_application(client, a_id)

        _act_as(b_id)
        resp = await client.get(f"/api/v1/applications/{app_id}/resume")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_stats_scoped_to_owner(self, client, two_users):
        a_id, b_id, factory = two_users
        await _seed_application(client, a_id)
        await _seed_application(client, a_id, company_name="A Two")

        # B has no applications → stats are all zero, never counting A's.
        _act_as(b_id)
        resp = await client.get("/api/v1/applications/stats")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ── Base résumé ───────────────────────────────────────────

class TestBaseResumeIsolation:
    @pytest.mark.asyncio
    async def test_base_resume_is_per_owner(self, client, two_users):
        a_id, b_id, factory = two_users

        _act_as(a_id)
        resp = await client.put("/api/v1/base-resume", json={"raw_text": "A's résumé"})
        assert resp.status_code == 200

        # B has no base résumé of their own yet.
        _act_as(b_id)
        resp = await client.get("/api/v1/base-resume")
        assert resp.status_code == 404

        # B sets their own — independent row, A's is untouched.
        resp = await client.put("/api/v1/base-resume", json={"raw_text": "B's résumé"})
        assert resp.status_code == 200
        resp = await client.get("/api/v1/base-resume")
        assert resp.json()["raw_text"] == "B's résumé"

        _act_as(a_id)
        resp = await client.get("/api/v1/base-resume")
        assert resp.json()["raw_text"] == "A's résumé"


# ── Generation history ────────────────────────────────────

class TestGenerationHistoryIsolation:
    @pytest.mark.asyncio
    async def test_history_and_stats_scoped(self, client, two_users):
        a_id, b_id, factory = two_users

        # Seed a generation row owned by A directly (the audit row is normally
        # written by the LLM path; we insert one to assert scoping).
        async with factory() as s:
            await s.execute(
                text(
                    "INSERT INTO resume_generations "
                    "(id, owner_id, status, total_tokens, duration_ms, preview, created_at, updated_at) "
                    "VALUES (:id, :owner, 'success', 150, 1000, false, now(), now())"
                ).bindparams(id=uuid.uuid4(), owner=a_id)
            )
            await s.commit()

        # B sees an empty history + zeroed stats — never A's row or tokens.
        _act_as(b_id)
        resp = await client.get("/api/v1/generation-history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["stats"]["total"] == 0
        assert body["stats"]["total_tokens"] == 0

        # A sees their own row.
        _act_as(a_id)
        resp = await client.get("/api/v1/generation-history")
        assert resp.json()["stats"]["total"] == 1
        assert resp.json()["stats"]["total_tokens"] == 150
