"""
Unit tests for application service layer.

DB is fully mocked — no live DB required.

Run:  pytest tests/unit/test_application_service.py -v
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.application import (
    ApplicationCreateRequest,
    ApplicationFilters,
    ApplicationStatus,
    ApplicationUpdateRequest,
)
from src.utils.exceptions import DuplicateError, NotFoundError


# ── Helpers ───────────────────────────────────────────────

def _today() -> date:
    return date.today()


def _mock_app(**overrides) -> MagicMock:
    """Returns a MagicMock that looks like a JobApplication ORM row."""
    app = MagicMock()
    app.id = overrides.get("id", uuid.uuid4())
    app.company_name = overrides.get("company_name", "Acme Corp")
    app.job_title = overrides.get("job_title", "Engineer")
    app.source = overrides.get("source", "manual")
    app.status = overrides.get("status", "applied")
    app.applied_date = overrides.get("applied_date", _today())
    app.job_id = overrides.get("job_id", None)
    app.job_url = None
    app.resume_version = None
    app.notes = None
    app.salary_range = None
    app.location = None
    app.address = None
    app.work_type = None
    app.contact_name = None
    app.contact_email = None
    app.follow_up_date = None
    app.created_at = datetime.now(timezone.utc)
    app.updated_at = datetime.now(timezone.utc)
    app.duplicate_warning = False
    return app


def _valid_create(**overrides) -> ApplicationCreateRequest:
    base = dict(
        company_name="Acme Corp",
        job_title="Engineer",
        source="manual",
        applied_date=str(_today()),
    )
    base.update(overrides)
    return ApplicationCreateRequest(**base)


def _make_db(app=None, scalar_result=None) -> AsyncMock:
    """Returns a mock AsyncSession."""
    db = AsyncMock()
    mock_app = app or _mock_app()

    # db.get() returns the mock app
    db.get = AsyncMock(return_value=mock_app)

    # db.execute() returns a result whose scalar_one_or_none / scalar_one works
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=scalar_result)
    exec_result.scalar_one = MagicMock(return_value=0)
    exec_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    db.execute = AsyncMock(return_value=exec_result)

    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db, mock_app


# ── create_application ────────────────────────────────────

class TestCreateApplication:
    @pytest.mark.asyncio
    async def test_creates_and_returns_response(self):
        from src.services.application_service import create_application
        db, mock_app = _make_db()

        with patch("src.services.application_service.ApplicationResponse.model_validate",
                   return_value=MagicMock(duplicate_warning=False)):
            result = await create_application(db, _valid_create())

        db.add.assert_called()
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_history_written_on_create(self):
        from src.services.application_service import create_application
        db, _ = _make_db()

        with patch("src.services.application_service.ApplicationResponse.model_validate",
                   return_value=MagicMock(duplicate_warning=False)):
            await create_application(db, _valid_create())

        # add() called at least twice: once for app, once for history
        assert db.add.call_count >= 2

    @pytest.mark.asyncio
    async def test_hard_duplicate_raises_409(self):
        from src.services.application_service import create_application
        db, _ = _make_db()

        # _check_duplicates finds existing record for company+job_id
        with patch(
            "src.services.application_service._check_duplicates",
            side_effect=DuplicateError("existing-uuid"),
        ):
            with pytest.raises(DuplicateError):
                await create_application(db, _valid_create(job_id="JOB123"))

    @pytest.mark.asyncio
    async def test_soft_duplicate_returns_warning_flag(self):
        from src.services.application_service import create_application
        db, _ = _make_db()

        mock_response = MagicMock()
        mock_response.duplicate_warning = False

        with patch("src.services.application_service._check_duplicates", return_value=True), \
             patch("src.services.application_service.ApplicationResponse.model_validate",
                   return_value=mock_response):
            result = await create_application(db, _valid_create())

        assert result.duplicate_warning is True

    @pytest.mark.asyncio
    async def test_reapplication_no_warning(self):
        from src.services.application_service import create_application
        db, _ = _make_db()

        mock_response = MagicMock()
        mock_response.duplicate_warning = False

        with patch("src.services.application_service._check_duplicates", return_value=False), \
             patch("src.services.application_service.ApplicationResponse.model_validate",
                   return_value=mock_response):
            result = await create_application(db, _valid_create())

        assert result.duplicate_warning is False


# ── update_application ────────────────────────────────────

class TestUpdateApplication:
    @pytest.mark.asyncio
    async def test_updates_only_provided_fields(self):
        from src.services.application_service import update_application
        db, mock_app = _make_db()

        with patch("src.services.application_service.ApplicationResponse.model_validate",
                   return_value=MagicMock()):
            await update_application(db, mock_app.id, ApplicationUpdateRequest(notes="new note"))

        assert mock_app.notes == "new note"

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        from src.services.application_service import update_application
        db, _ = _make_db()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await update_application(db, uuid.uuid4(), ApplicationUpdateRequest(notes="x"))

    @pytest.mark.asyncio
    async def test_status_change_writes_history(self):
        from src.services.application_service import update_application
        db, mock_app = _make_db()
        mock_app.status = "applied"

        with patch("src.services.application_service.ApplicationResponse.model_validate",
                   return_value=MagicMock()):
            await update_application(
                db, mock_app.id, ApplicationUpdateRequest(status="interview")
            )

        # History row added
        assert db.add.call_count >= 1

    @pytest.mark.asyncio
    async def test_same_status_patch_no_history(self):
        from src.services.application_service import update_application
        db, mock_app = _make_db()
        mock_app.status = "applied"

        with patch("src.services.application_service.ApplicationResponse.model_validate",
                   return_value=MagicMock()):
            await update_application(
                db, mock_app.id, ApplicationUpdateRequest(status="applied")
            )

        # add() NOT called for history (status unchanged)
        db.add.assert_not_called()


# ── get_application_by_id ─────────────────────────────────

class TestGetApplicationById:
    @pytest.mark.asyncio
    async def test_returns_response(self):
        from src.services.application_service import get_application_by_id
        db, mock_app = _make_db()

        with patch("src.services.application_service.ApplicationResponse.model_validate",
                   return_value=MagicMock()):
            result = await get_application_by_id(db, mock_app.id)

        assert result is not None

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        from src.services.application_service import get_application_by_id
        db, _ = _make_db()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await get_application_by_id(db, uuid.uuid4())


# ── get_applications ──────────────────────────────────────

class TestGetApplications:
    @pytest.mark.asyncio
    async def test_returns_list_response(self):
        from src.services.application_service import get_applications
        db, _ = _make_db()

        result = await get_applications(db, ApplicationFilters())
        assert result.data == []
        assert result.pagination.total == 0

    @pytest.mark.asyncio
    async def test_empty_filters_returns_empty_not_404(self):
        from src.services.application_service import get_applications
        db, _ = _make_db()

        result = await get_applications(db, ApplicationFilters())
        assert result.data == []

    @pytest.mark.asyncio
    async def test_page_beyond_total_returns_empty(self):
        from src.services.application_service import get_applications
        db, _ = _make_db()

        result = await get_applications(db, ApplicationFilters(page=99))
        assert result.data == []

    @pytest.mark.asyncio
    async def test_limit_clamped_to_100(self):
        from src.services.application_service import get_applications
        db, _ = _make_db()

        # Schema enforces max 100 — verify it doesn't blow up
        filters = ApplicationFilters(limit=100)
        result = await get_applications(db, filters)
        assert result.pagination.limit == 100

    @pytest.mark.asyncio
    async def test_date_from_after_date_to_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ApplicationFilters(
                date_from=date(2026, 3, 10),
                date_to=date(2026, 3, 1),
            )


# ── get_stats ────────────────────────────────────────────

class TestGetStats:
    """get_stats now issues three queries: headline counts, source breakdown,
    weekly trend. Tests mock all three via db.execute side_effect."""

    @staticmethod
    def _mock_execute_for(counts_row, source_rows, trend_rows):
        counts_result = MagicMock(); counts_result.one = MagicMock(return_value=counts_row)
        source_result = MagicMock(); source_result.all = MagicMock(return_value=source_rows)
        trend_result = MagicMock(); trend_result.all = MagicMock(return_value=trend_rows)
        return AsyncMock(side_effect=[counts_result, source_result, trend_result])

    @pytest.mark.asyncio
    async def test_returns_stats_response(self):
        from src.services.application_service import get_stats
        db = AsyncMock()
        counts = MagicMock(
            total=5, interview=1, assessment=1, rejected=2, offer=1, needs_review=1
        )
        source_rows = [("manual", 2), ("resume_generator", 3)]
        trend_rows = [(date(2026, 5, 18), 3), (date(2026, 5, 25), 2)]
        db.execute = self._mock_execute_for(counts, source_rows, trend_rows)

        stats = await get_stats(db)
        assert stats.total == 5
        assert stats.interview == 1
        assert stats.rejected == 2
        assert stats.offer == 1
        assert stats.needs_review == 1
        # ATS pass rate = (assessment + interview + offer) / total = 3/5
        assert stats.ats_pass_rate == pytest.approx(0.6)
        assert stats.source_breakdown.manual == 2
        assert stats.source_breakdown.resume_generator == 3
        assert len(stats.weekly_trend) == 2
        assert stats.weekly_trend[0].count == 3

    @pytest.mark.asyncio
    async def test_returns_zeros_when_empty(self):
        from src.services.application_service import get_stats
        db = AsyncMock()
        counts = MagicMock(
            total=0, interview=0, assessment=0, rejected=0, offer=0, needs_review=0
        )
        db.execute = self._mock_execute_for(counts, [], [])

        stats = await get_stats(db)
        assert stats.total == 0
        assert stats.ats_pass_rate == 0.0
        assert stats.source_breakdown.manual == 0
        assert stats.source_breakdown.resume_generator == 0
        assert stats.weekly_trend == []


# ── get_status_history ────────────────────────────────────

class TestGetStatusHistory:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_history(self):
        from src.services.application_service import get_status_history
        db, mock_app = _make_db()

        result = await get_status_history(db, mock_app.id)
        assert result == []

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        from src.services.application_service import get_status_history
        db, _ = _make_db()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await get_status_history(db, uuid.uuid4())
