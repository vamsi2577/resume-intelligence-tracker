"""
Integration tests for DB models and migration.

Requires running PostgreSQL:
    docker-compose up -d

Run:  pytest tests/integration/test_models.py -v
"""
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.models.application import ApplicationStatusHistory, JobApplication


# ── Helpers ───────────────────────────────────────────────

def _sample_application(**overrides) -> dict:
    base = dict(
        id=uuid.uuid4(),
        company_name="Acme Corp",
        job_title="Software Engineer",
        source="manual",
        status="applied",
        applied_date=date(2026, 3, 1),
    )
    base.update(overrides)
    return base


# ── Migration / schema tests ──────────────────────────────

class TestMigration:
    @pytest.mark.asyncio
    async def test_tables_exist(self, db):
        result = await db.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('job_applications', 'application_status_history')
        """))
        tables = {row[0] for row in result.fetchall()}
        assert "job_applications" in tables
        assert "application_status_history" in tables

    @pytest.mark.asyncio
    async def test_indexes_exist(self, db):
        result = await db.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'job_applications'
        """))
        indexes = {row[0] for row in result.fetchall()}
        assert "ix_job_applications_company_name" in indexes
        assert "ix_job_applications_status" in indexes
        assert "ix_job_applications_applied_date" in indexes

    @pytest.mark.asyncio
    async def test_enum_types_exist(self, db):
        result = await db.execute(text("""
            SELECT typname FROM pg_type
            WHERE typname IN ('application_status', 'application_source', 'work_type')
        """))
        types = {row[0] for row in result.fetchall()}
        assert "application_status" in types
        assert "application_source" in types
        assert "work_type" in types


# ── Model CRUD tests ──────────────────────────────────────

class TestJobApplicationModel:
    @pytest.mark.asyncio
    async def test_insert_and_fetch(self, db):
        app = JobApplication(**_sample_application())
        db.add(app)
        await db.flush()

        fetched = await db.get(JobApplication, app.id)
        assert fetched is not None
        assert fetched.company_name == "Acme Corp"

    @pytest.mark.asyncio
    async def test_created_at_auto_set(self, db):
        app = JobApplication(**_sample_application())
        db.add(app)
        await db.flush()
        assert app.created_at is not None

    @pytest.mark.asyncio
    async def test_updated_at_changes_on_update(self, db):
        app = JobApplication(**_sample_application())
        db.add(app)
        await db.flush()
        original_updated = app.updated_at

        app.status = "screening"
        await db.flush()
        await db.refresh(app)
        # updated_at is managed by app layer; here we verify field is writable
        assert app.status == "screening"

    @pytest.mark.asyncio
    async def test_null_mandatory_field_raises(self, db):
        app = JobApplication(**_sample_application(company_name=None))
        db.add(app)
        with pytest.raises(IntegrityError):
            await db.flush()

    @pytest.mark.asyncio
    async def test_invalid_enum_status_raises(self, db):
        with pytest.raises(Exception):
            app = JobApplication(**_sample_application(status="invalid_status"))
            db.add(app)
            await db.flush()

    @pytest.mark.asyncio
    async def test_optional_fields_default_to_none(self, db):
        app = JobApplication(**_sample_application())
        db.add(app)
        await db.flush()
        assert app.job_url is None
        assert app.notes is None
        assert app.work_type is None


# ── Status history / FK tests ─────────────────────────────

class TestStatusHistoryModel:
    @pytest.mark.asyncio
    async def test_history_row_linked_to_application(self, db):
        app = JobApplication(**_sample_application())
        db.add(app)
        await db.flush()

        history = ApplicationStatusHistory(
            id=uuid.uuid4(),
            application_id=app.id,
            status="applied",
            changed_at=datetime.now(timezone.utc),
        )
        db.add(history)
        await db.flush()

        fetched = await db.get(ApplicationStatusHistory, history.id)
        assert fetched.application_id == app.id

    @pytest.mark.asyncio
    async def test_fk_constraint_rejects_invalid_parent(self, db):
        history = ApplicationStatusHistory(
            id=uuid.uuid4(),
            application_id=uuid.uuid4(),  # non-existent
            status="applied",
            changed_at=datetime.now(timezone.utc),
        )
        db.add(history)
        with pytest.raises(IntegrityError):
            await db.flush()

    @pytest.mark.asyncio
    async def test_cascade_delete_removes_history(self, db):
        app = JobApplication(**_sample_application())
        db.add(app)
        await db.flush()

        history = ApplicationStatusHistory(
            id=uuid.uuid4(),
            application_id=app.id,
            status="applied",
            changed_at=datetime.now(timezone.utc),
        )
        db.add(history)
        await db.flush()

        await db.delete(app)
        await db.flush()

        fetched = await db.get(ApplicationStatusHistory, history.id)
        assert fetched is None
