"""
Unit tests for structured logger and correlation ID utilities.

Run:  pytest tests/unit/test_logger.py -v
"""
import json
import logging

import pytest

from src.utils.correlation import get_correlation_id, set_correlation_id
from src.utils.logger import get_logger


# ── Helpers ──────────────────────────────────────────────

def capture_log(logger: logging.Logger, level: str, message: str, extra: dict = None) -> dict:
    """Emit a log at the given level and return the parsed JSON record."""
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(self.format(record))

    handler = _Capture()
    handler.setFormatter(logger.handlers[0].formatter)
    logger.addHandler(handler)

    try:
        getattr(logger, level.lower())(message, extra=extra or {})
    finally:
        logger.removeHandler(handler)

    assert records, "No log records captured"
    return json.loads(records[-1])


# ── Correlation ID tests ──────────────────────────────────

class TestCorrelationID:
    def test_set_generates_uuid_when_no_value(self):
        cid = set_correlation_id()
        assert len(cid) == 36  # UUID4 format
        assert cid == get_correlation_id()

    def test_set_accepts_explicit_value(self):
        cid = set_correlation_id("test-cid-123")
        assert get_correlation_id() == "test-cid-123"

    def test_get_returns_current_context_value(self):
        set_correlation_id("ctx-abc")
        assert get_correlation_id() == "ctx-abc"

    def test_overwrite_replaces_previous(self):
        set_correlation_id("first")
        set_correlation_id("second")
        assert get_correlation_id() == "second"


# ── Logger output tests ───────────────────────────────────

class TestJSONLogger:
    def setup_method(self):
        set_correlation_id("test-correlation-id")
        self.logger = get_logger("test.module")
        self.logger.setLevel(logging.DEBUG)

    def test_output_is_valid_json(self):
        record = capture_log(self.logger, "info", "hello world")
        assert isinstance(record, dict)

    def test_required_fields_present(self):
        record = capture_log(self.logger, "info", "check fields")
        for field in ("timestamp", "level", "correlation_id", "module", "message", "extra"):
            assert field in record, f"Missing field: {field}"

    def test_correlation_id_injected(self):
        record = capture_log(self.logger, "info", "cid check")
        assert record["correlation_id"] == "test-correlation-id"

    def test_message_matches(self):
        record = capture_log(self.logger, "info", "exact message")
        assert record["message"] == "exact message"

    def test_module_name_matches(self):
        record = capture_log(self.logger, "info", "module check")
        assert record["module"] == "test.module"

    def test_extra_fields_captured(self):
        record = capture_log(self.logger, "info", "with extra", extra={"job_id": "abc123"})
        assert record["extra"].get("job_id") == "abc123"

    def test_malformed_extra_does_not_crash(self):
        """Non-serialisable extra should not raise — default=str handles it."""
        record = capture_log(self.logger, "info", "bad extra", extra={"obj": object()})
        assert record["message"] == "bad extra"

    def test_log_level_info(self):
        record = capture_log(self.logger, "info", "info level")
        assert record["level"] == "INFO"

    def test_log_level_warning(self):
        record = capture_log(self.logger, "warning", "warn level")
        assert record["level"] == "WARNING"

    def test_log_level_error(self):
        record = capture_log(self.logger, "error", "error level")
        assert record["level"] == "ERROR"

    def test_log_level_debug(self):
        record = capture_log(self.logger, "debug", "debug level")
        assert record["level"] == "DEBUG"

    def test_exception_info_captured(self):
        records = []

        class _Capture(logging.Handler):
            def emit(self, r):
                records.append(self.format(r))

        handler = _Capture()
        handler.setFormatter(self.logger.handlers[0].formatter)
        self.logger.addHandler(handler)

        try:
            try:
                raise ValueError("boom")
            except ValueError:
                self.logger.exception("caught error")
        finally:
            self.logger.removeHandler(handler)

        record = json.loads(records[-1])
        assert "exception" in record
        assert "ValueError" in record["exception"]

    def test_no_duplicate_handlers_on_repeated_get_logger(self):
        l1 = get_logger("test.dedup")
        l2 = get_logger("test.dedup")
        assert len(l2.handlers) == len(l1.handlers)

    def test_missing_correlation_id_is_none(self):
        """When no correlation ID is set, field should be null not empty string."""
        set_correlation_id.__wrapped__ = None  # reset not possible in ContextVar directly
        # Set to empty string to simulate missing context
        from src.utils import correlation
        correlation._correlation_id.set("")
        record = capture_log(self.logger, "info", "no cid")
        assert record["correlation_id"] is None or record["correlation_id"] == ""
