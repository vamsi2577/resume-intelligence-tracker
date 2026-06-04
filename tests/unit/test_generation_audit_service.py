"""
Unit tests for generation_audit_service.

The audit decorator and stats math are tested with the DB write stubbed —
no real database.

Run:  pytest tests/unit/test_generation_audit_service.py -v
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import generation_audit_service as audit
from src.services.llm_client import LLMError
from src.utils.exceptions import NotFoundError, ValidationError


OWNER = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _payload(**over):
    base = dict(
        job_description="A sufficiently long job description.",
        target_company="Acme",
        job_title="Engineer",
    )
    base.update(over)
    return SimpleNamespace(**base)


# ── Decorator records the right status ─────────────────────

@pytest.mark.asyncio
async def test_records_success():
    @audit.track_llm_call
    async def fn(db, owner, payload):
        return "result"

    with patch.object(audit, "_persist", new=AsyncMock(return_value=None)) as p:
        out = await fn(AsyncMock(), OWNER, _payload())

    assert out == "result"
    assert p.call_args.kwargs["status"] == "success"


@pytest.mark.asyncio
async def test_records_llm_error_and_reraises():
    @audit.track_llm_call
    async def fn(db, owner, payload):
        raise LLMError("upstream 500")

    with patch.object(audit, "_persist", new=AsyncMock(return_value=None)) as p:
        with pytest.raises(LLMError):
            await fn(AsyncMock(), OWNER, _payload())

    assert p.call_args.kwargs["status"] == "llm_error"
    assert "upstream 500" in p.call_args.kwargs["error_message"]


@pytest.mark.asyncio
async def test_records_validation_error_and_reraises():
    @audit.track_llm_call
    async def fn(db, owner, payload):
        raise ValidationError("bad schema")

    with patch.object(audit, "_persist", new=AsyncMock(return_value=None)) as p:
        with pytest.raises(ValidationError):
            await fn(AsyncMock(), OWNER, _payload())

    assert p.call_args.kwargs["status"] == "validation_error"


@pytest.mark.asyncio
async def test_does_not_record_missing_base_resume():
    """No base résumé → nothing generated → no audit row."""
    @audit.track_llm_call
    async def fn(db, owner, payload):
        raise NotFoundError("base_resume", str(OWNER))

    with patch.object(audit, "_persist", new=AsyncMock(return_value=None)) as p:
        with pytest.raises(NotFoundError):
            await fn(AsyncMock(), OWNER, _payload())

    p.assert_not_called()


# ── _persist captures telemetry + raw output policy ────────

@pytest.mark.asyncio
async def test_persist_attaches_raw_output_on_failure_only():
    from src.utils.llm_context import set_llm_meta, LLMCallMeta

    set_llm_meta(LLMCallMeta(
        model="llama3", provider="groq",
        prompt_tokens=100, completion_tokens=50, total_tokens=150,
        raw_content="{bad json", duration_ms=1234,
    ))

    captured = {}

    class _Sess:
        def add(self, row): captured["row"] = row
        async def commit(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    with patch.object(audit, "AsyncSessionFactory", lambda: _Sess()):
        # failure → raw output retained
        await audit._persist(owner_id=OWNER, payload=_payload(),
                             status="llm_error", error_message="boom", wrapper_ms=9999)
        assert captured["row"].llm_raw_output == "{bad json"
        assert captured["row"].total_tokens == 150
        assert captured["row"].duration_ms == 1234   # prefers LLM time over wrapper

        # success → raw output dropped
        await audit._persist(owner_id=OWNER, payload=_payload(),
                             status="success", wrapper_ms=10)
        assert captured["row"].llm_raw_output is None


# ── get_stats aggregation ──────────────────────────────────

@pytest.mark.asyncio
async def test_get_stats_math():
    # get_stats now aggregates in SQL and reads one result row.
    agg = SimpleNamespace(
        total=4, success=2, llm_error=1, validation_error=1,
        avg_duration=150.0, total_tokens=610,
    )
    db = AsyncMock()
    result = MagicMock()
    result.one = MagicMock(return_value=agg)
    db.execute = AsyncMock(return_value=result)

    stats = await audit.get_stats(db)

    assert stats.total == 4
    assert stats.success == 2
    assert stats.llm_error == 1
    assert stats.validation_error == 1
    assert stats.success_rate == 0.5
    assert stats.avg_duration_ms == 150
    assert stats.total_tokens == 610


@pytest.mark.asyncio
async def test_get_stats_empty():
    agg = SimpleNamespace(
        total=0, success=0, llm_error=0, validation_error=0,
        avg_duration=None, total_tokens=0,
    )
    db = AsyncMock()
    result = MagicMock()
    result.one = MagicMock(return_value=agg)
    db.execute = AsyncMock(return_value=result)

    stats = await audit.get_stats(db)
    assert stats.total == 0
    assert stats.success_rate == 0.0
    assert stats.avg_duration_ms is None
