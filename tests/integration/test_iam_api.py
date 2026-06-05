"""
IAM enforcement integration tests (Phase 1b).

Exercises the real authorization path against Postgres: effective-permission
resolution (direct roles + roles via group membership), require_permission
gating (403), /auth/me, and the admin user/role routes incl. audit logging.

Uses a per-test NullPool engine + get_db override (the app's module-level
engine breaks under pytest-asyncio per-test loops), same as the tenant
isolation suite.

Run:  pytest tests/integration/test_iam_api.py -v
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.deps import get_current_owner
from src.core.config import settings
from src.core.permissions import Permissions
from src.db.session import get_db
from src.main import app

DEFAULT_OWNER = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest_asyncio.fixture
async def iam():
    """Per-test engine + get_db override + a factory for seeding."""
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
    await engine.dispose()


def _act_as(owner_id: uuid.UUID) -> None:
    app.dependency_overrides[get_current_owner] = lambda: owner_id


async def _make_user(factory, *, roles: list[str] | None = None, groups: list[str] | None = None) -> uuid.UUID:
    """Create a user; optionally grant direct roles and group memberships
    (each group is created with the given role names attached)."""
    uid = uuid.uuid4()
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO users (id, email, is_active, created_at, updated_at) "
            "VALUES (:id, :email, true, now(), now())"
        ).bindparams(id=uid, email=f"{uid}@iam.test"))
        for role_name in (roles or []):
            await s.execute(text(
                "INSERT INTO user_roles (user_id, role_id, granted_at, created_at, updated_at) "
                "SELECT :uid, id, now(), now(), now() FROM roles WHERE name = :rn"
            ).bindparams(uid=uid, rn=role_name))
        for group_role in (groups or []):
            gid = uuid.uuid4()
            await s.execute(text(
                "INSERT INTO groups (id, name, created_at, updated_at) "
                "VALUES (:gid, :name, now(), now())"
            ).bindparams(gid=gid, name=f"grp-{gid}"))
            await s.execute(text(
                "INSERT INTO group_roles (group_id, role_id, created_at, updated_at) "
                "SELECT :gid, id, now(), now() FROM roles WHERE name = :rn"
            ).bindparams(gid=gid, rn=group_role))
            await s.execute(text(
                "INSERT INTO group_members (group_id, user_id, added_at, created_at, updated_at) "
                "VALUES (:gid, :uid, now(), now(), now())"
            ).bindparams(gid=gid, uid=uid))
        await s.commit()
    return uid


async def _cleanup(factory, *ids: uuid.UUID) -> None:
    async with factory() as s:
        await s.execute(text("DELETE FROM users WHERE id = ANY(:ids)").bindparams(ids=list(ids)))
        await s.commit()


# ── /auth/me ──────────────────────────────────────────────

class TestAuthMe:
    @pytest.mark.asyncio
    async def test_default_owner_is_superadmin(self, client, iam):
        _act_as(DEFAULT_OWNER)
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == str(DEFAULT_OWNER)
        assert set(body["roles"]) == {"user", "superadmin"}
        # superadmin path → has the admin-only perms AND the self-service ones.
        assert Permissions.ROLES_MANAGE in body["permissions"]
        assert Permissions.APPLICATIONS_READ_OWN in body["permissions"]

    @pytest.mark.asyncio
    async def test_plain_user_permissions(self, client, iam):
        uid = await _make_user(iam, roles=["user"])
        _act_as(uid)
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        perms = resp.json()["permissions"]
        assert Permissions.APPLICATIONS_READ_OWN in perms
        assert Permissions.USERS_MANAGE not in perms  # no admin powers
        await _cleanup(iam, uid)


# ── require_permission gating ─────────────────────────────

class TestPermissionGating:
    @pytest.mark.asyncio
    async def test_plain_user_cannot_list_users(self, client, iam):
        uid = await _make_user(iam, roles=["user"])
        _act_as(uid)
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code == 403
        await _cleanup(iam, uid)

    @pytest.mark.asyncio
    async def test_admin_can_list_users(self, client, iam):
        uid = await _make_user(iam, roles=["admin"])
        _act_as(uid)
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        await _cleanup(iam, uid)

    @pytest.mark.asyncio
    async def test_support_cannot_manage_roles(self, client, iam):
        # support has admin.access + read.any, but NOT roles.manage.
        uid = await _make_user(iam, roles=["support"])
        _act_as(uid)
        resp = await client.get("/api/v1/admin/roles")
        assert resp.status_code == 403
        await _cleanup(iam, uid)

    @pytest.mark.asyncio
    async def test_permission_via_group_membership(self, client, iam):
        # No direct role; gets `admin` purely through a group.
        uid = await _make_user(iam, groups=["admin"])
        _act_as(uid)
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        await _cleanup(iam, uid)


# ── Admin user + role management (audit-logged) ───────────

class TestAdminUserManagement:
    @pytest.mark.asyncio
    async def test_assign_and_revoke_role_writes_audit(self, client, iam):
        target = await _make_user(iam, roles=["user"])
        _act_as(DEFAULT_OWNER)  # superadmin actor

        resp = await client.post(
            f"/api/v1/admin/users/{target}/roles", json={"role": "support"}
        )
        assert resp.status_code == 200
        assert set(resp.json()["roles"]) == {"user", "support"}

        resp = await client.delete(f"/api/v1/admin/users/{target}/roles/support")
        assert resp.status_code == 200
        assert resp.json()["roles"] == ["user"]

        # Two audit rows: grant + revoke, by the acting superadmin.
        async with iam() as s:
            rows = (await s.execute(text(
                "SELECT action FROM iam_audit_log WHERE target_user_id = :t ORDER BY created_at"
            ).bindparams(t=target))).all()
        actions = [r[0] for r in rows]
        assert "role.grant" in actions and "role.revoke" in actions

        await _cleanup(iam, target)

    @pytest.mark.asyncio
    async def test_deactivate_user(self, client, iam):
        target = await _make_user(iam, roles=["user"])
        _act_as(DEFAULT_OWNER)
        resp = await client.post(f"/api/v1/admin/users/{target}/deactivate")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False
        await _cleanup(iam, target)

    @pytest.mark.asyncio
    async def test_assign_unknown_role_404(self, client, iam):
        target = await _make_user(iam, roles=["user"])
        _act_as(DEFAULT_OWNER)
        resp = await client.post(
            f"/api/v1/admin/users/{target}/roles", json={"role": "wizard"}
        )
        assert resp.status_code == 404
        await _cleanup(iam, target)
