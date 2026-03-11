"""
Unit tests for src/utils/metrics.py

Run: pytest tests/unit/test_metrics.py -v
"""
import time
import pytest

from src.utils import metrics


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics.reset()
    yield
    metrics.reset()


# ── record_request ────────────────────────────────────────

class TestRecordRequest:
    def test_latency_recorded_per_endpoint(self):
        metrics.record_request("/api/v1/log-application", "POST", 201, 45.3)
        snap = metrics.get_snapshot()
        assert "POST /api/v1/log-application" in snap["requests"]["latency_ms"]
        assert snap["requests"]["latency_ms"]["POST /api/v1/log-application"]["count"] == 1

    def test_zero_duration(self):
        metrics.record_request("/api/v1/applications", "GET", 200, 0.0)
        snap = metrics.get_snapshot()
        stats = snap["requests"]["latency_ms"]["GET /api/v1/applications"]
        assert stats["min"] == 0.0
        assert stats["avg"] == 0.0

    def test_negative_duration_clamped_to_zero(self):
        metrics.record_request("/api/v1/applications", "GET", 200, -5.0)
        snap = metrics.get_snapshot()
        stats = snap["requests"]["latency_ms"]["GET /api/v1/applications"]
        assert stats["min"] >= 0.0

    def test_multiple_requests_accumulate(self):
        for d in [10.0, 20.0, 30.0]:
            metrics.record_request("/health", "GET", 200, d)
        stats = metrics.get_snapshot()["requests"]["latency_ms"]["GET /health"]
        assert stats["count"] == 3
        assert stats["avg"] == 20.0

    def test_p95_calculation(self):
        for i in range(20):
            metrics.record_request("/health", "GET", 200, float(i + 1))
        stats = metrics.get_snapshot()["requests"]["latency_ms"]["GET /health"]
        assert stats["p95"] >= stats["avg"]


# ── status counters ───────────────────────────────────────

class TestStatusCounters:
    def test_2xx_success_counted(self):
        metrics.record_request("/api/v1/log-application", "POST", 201, 10.0)
        snap = metrics.get_snapshot()
        assert snap["requests"]["by_status"].get("2xx", 0) == 1
        assert snap["requests"]["success_rate"] == 1.0

    def test_4xx_increments_failure(self):
        metrics.record_request("/api/v1/applications/bad", "GET", 404, 5.0)
        snap = metrics.get_snapshot()
        assert snap["requests"]["by_status"].get("4xx", 0) == 1
        assert snap["requests"]["failure_rate"] == 1.0

    def test_5xx_increments_failure(self):
        metrics.record_request("/api/v1/log-application", "POST", 500, 5.0)
        snap = metrics.get_snapshot()
        assert snap["requests"]["failure_rate"] == 1.0

    def test_mixed_success_failure_rate(self):
        metrics.record_request("/health", "GET", 200, 1.0)
        metrics.record_request("/health", "GET", 200, 1.0)
        metrics.record_request("/health", "GET", 500, 1.0)
        snap = metrics.get_snapshot()
        assert snap["requests"]["failure_rate"] == pytest.approx(1 / 3, rel=0.01)

    def test_empty_state_defaults(self):
        snap = metrics.get_snapshot()
        assert snap["requests"]["total"] == 0
        assert snap["requests"]["success_rate"] == 1.0
        assert snap["requests"]["failure_rate"] == 0.0


# ── record_parse_failure ──────────────────────────────────

class TestParseFailure:
    def test_parse_failure_increments_on_422(self):
        metrics.record_parse_failure("/api/v1/log-application")
        snap = metrics.get_snapshot()
        assert snap["parse_failures"]["total"] == 1
        assert snap["parse_failures"]["by_endpoint"]["/api/v1/log-application"] == 1

    def test_multiple_endpoints_tracked_separately(self):
        metrics.record_parse_failure("/api/v1/log-application")
        metrics.record_parse_failure("/api/v1/applications")
        metrics.record_parse_failure("/api/v1/log-application")
        snap = metrics.get_snapshot()
        assert snap["parse_failures"]["total"] == 3
        assert snap["parse_failures"]["by_endpoint"]["/api/v1/log-application"] == 2

    def test_parse_failure_zero_on_fresh_state(self):
        snap = metrics.get_snapshot()
        assert snap["parse_failures"]["total"] == 0


# ── record_db_query ───────────────────────────────────────

class TestDbQueryMetrics:
    def test_db_latency_recorded(self):
        metrics.record_db_query("create_application", 12.5)
        snap = metrics.get_snapshot()
        assert "create_application" in snap["db_queries"]["latency_ms"]
        assert snap["db_queries"]["latency_ms"]["create_application"]["count"] == 1

    def test_multiple_operations_tracked(self):
        metrics.record_db_query("get_applications", 8.0)
        metrics.record_db_query("get_applications", 12.0)
        metrics.record_db_query("get_application_by_id", 5.0)
        snap = metrics.get_snapshot()
        assert snap["db_queries"]["latency_ms"]["get_applications"]["count"] == 2
        assert snap["db_queries"]["latency_ms"]["get_application_by_id"]["count"] == 1


# ── track_db_query decorator ──────────────────────────────

class TestTrackDbQueryDecorator:
    @pytest.mark.asyncio
    async def test_decorator_records_latency(self):
        @metrics.track_db_query("test_op")
        async def fake_db_call():
            return "result"

        result = await fake_db_call()
        assert result == "result"
        snap = metrics.get_snapshot()
        assert snap["db_queries"]["latency_ms"]["test_op"]["count"] == 1

    @pytest.mark.asyncio
    async def test_decorator_records_on_exception(self):
        @metrics.track_db_query("failing_op")
        async def failing_call():
            raise ValueError("db error")

        with pytest.raises(ValueError):
            await failing_call()

        snap = metrics.get_snapshot()
        assert snap["db_queries"]["latency_ms"]["failing_op"]["count"] == 1


# ── get_snapshot structure ────────────────────────────────

class TestSnapshotStructure:
    def test_snapshot_has_all_top_level_keys(self):
        snap = metrics.get_snapshot()
        assert "requests" in snap
        assert "parse_failures" in snap
        assert "db_queries" in snap

    def test_requests_has_required_keys(self):
        snap = metrics.get_snapshot()
        req = snap["requests"]
        for key in ("total", "by_status", "success_rate", "failure_rate", "latency_ms"):
            assert key in req
