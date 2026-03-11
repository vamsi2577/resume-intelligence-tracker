"""
Unit tests for Pydantic schemas.

No DB required — pure validation tests.

Run:  pytest tests/unit/test_schemas.py -v
"""
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from src.schemas.application import (
    ApplicationCreateRequest,
    ApplicationUpdateRequest,
    ApplicationListResponse,
    ApplicationResponse,
    PaginationMeta,
    StatusHistoryResponse,
)


# ── Helpers ───────────────────────────────────────────────

def _today() -> date:
    return date.today()


def _future() -> date:
    return date.today() + timedelta(days=1)


def _past() -> date:
    return date.today() - timedelta(days=10)


def _valid_create(**overrides) -> dict:
    base = dict(
        company_name="Acme Corp",
        job_title="Software Engineer",
        source="manual",
        applied_date=str(_today()),
    )
    base.update(overrides)
    return base


# ── ApplicationCreateRequest ──────────────────────────────

class TestApplicationCreateRequest:
    def test_valid_payload_passes(self):
        req = ApplicationCreateRequest(**_valid_create())
        assert req.company_name == "Acme Corp"

    def test_missing_company_name_raises(self):
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(**_valid_create(company_name=None))

    def test_missing_job_title_raises(self):
        with pytest.raises(ValidationError):
            data = _valid_create()
            del data["job_title"]
            ApplicationCreateRequest(**data)

    def test_missing_source_raises(self):
        with pytest.raises(ValidationError):
            data = _valid_create()
            del data["source"]
            ApplicationCreateRequest(**data)

    def test_missing_applied_date_raises(self):
        with pytest.raises(ValidationError):
            data = _valid_create()
            del data["applied_date"]
            ApplicationCreateRequest(**data)

    def test_applied_date_in_future_raises(self):
        with pytest.raises(ValidationError, match="future"):
            ApplicationCreateRequest(**_valid_create(applied_date=str(_future())))

    def test_applied_date_today_passes(self):
        req = ApplicationCreateRequest(**_valid_create(applied_date=str(_today())))
        assert req.applied_date == _today()

    def test_follow_up_date_in_future_raises(self):
        with pytest.raises(ValidationError, match="future"):
            ApplicationCreateRequest(**_valid_create(follow_up_date=str(_future())))

    def test_follow_up_date_in_past_passes(self):
        req = ApplicationCreateRequest(**_valid_create(follow_up_date=str(_past())))
        assert req.follow_up_date == _past()

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(**_valid_create(contact_email="not-an-email"))

    def test_valid_email_passes(self):
        req = ApplicationCreateRequest(**_valid_create(contact_email="user@example.com"))
        assert req.contact_email == "user@example.com"

    def test_invalid_url_raises(self):
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(**_valid_create(job_url="not-a-url"))

    def test_valid_url_passes(self):
        req = ApplicationCreateRequest(**_valid_create(job_url="https://jobs.example.com/123"))
        assert req.job_url == "https://jobs.example.com/123"

    def test_invalid_status_enum_raises(self):
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(**_valid_create(status="promoted"))

    def test_invalid_source_enum_raises(self):
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(**_valid_create(source="email"))

    def test_invalid_work_type_raises(self):
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(**_valid_create(work_type="contract"))

    def test_optional_fields_default_to_none(self):
        req = ApplicationCreateRequest(**_valid_create())
        assert req.job_url is None
        assert req.notes is None
        assert req.work_type is None
        assert req.contact_email is None

    def test_status_defaults_to_applied(self):
        req = ApplicationCreateRequest(**_valid_create())
        assert req.status.value == "applied"

    def test_extra_unknown_fields_rejected(self):
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(**_valid_create(unknown_field="value"))

    def test_ftp_url_rejected(self):
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(**_valid_create(job_url="ftp://example.com/file"))

    def test_company_name_empty_string_raises(self):
        with pytest.raises(ValidationError):
            ApplicationCreateRequest(**_valid_create(company_name=""))


# ── ApplicationUpdateRequest ──────────────────────────────

class TestApplicationUpdateRequest:
    def test_partial_update_passes(self):
        req = ApplicationUpdateRequest(status="interview")
        assert req.status.value == "interview"

    def test_empty_body_raises(self):
        with pytest.raises(ValidationError, match="at least one"):
            ApplicationUpdateRequest()

    def test_all_none_raises(self):
        with pytest.raises(ValidationError, match="at least one"):
            ApplicationUpdateRequest(
                company_name=None,
                job_title=None,
                status=None,
            )

    def test_single_field_passes(self):
        req = ApplicationUpdateRequest(notes="Following up")
        assert req.notes == "Following up"

    def test_future_applied_date_raises(self):
        with pytest.raises(ValidationError, match="future"):
            ApplicationUpdateRequest(applied_date=str(_future()))

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError):
            ApplicationUpdateRequest(contact_email="bad")

    def test_invalid_url_raises(self):
        with pytest.raises(ValidationError):
            ApplicationUpdateRequest(job_url="bad-url")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            ApplicationUpdateRequest(status="applied", mystery="field")

    def test_valid_status_change(self):
        req = ApplicationUpdateRequest(status="offer")
        assert req.status.value == "offer"


# ── PaginationMeta ────────────────────────────────────────

class TestPaginationMeta:
    def test_valid_pagination(self):
        meta = PaginationMeta(page=1, limit=20, total=100, total_pages=5)
        assert meta.total_pages == 5

    def test_all_fields_required(self):
        with pytest.raises(ValidationError):
            PaginationMeta(page=1, limit=20)


# ── ApplicationListResponse ───────────────────────────────

class TestApplicationListResponse:
    def test_empty_data_valid(self):
        resp = ApplicationListResponse(
            data=[],
            pagination=PaginationMeta(page=1, limit=20, total=0, total_pages=0),
        )
        assert resp.data == []
        assert resp.meta == {}
