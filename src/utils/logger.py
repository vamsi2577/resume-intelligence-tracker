"""
Structured JSON logger.

Usage in any module:
    from src.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("message", extra={"key": "value"})

Every log line is a JSON object with:
    timestamp, level, correlation_id, module, message, extra
"""
import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from src.utils.correlation import get_correlation_id


class _JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        # Base payload
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "correlation_id": get_correlation_id() or None,
            "module": record.name,
            "message": record.getMessage(),
            "extra": {},
        }

        # Collect any extra fields passed via logger.info("msg", extra={...})
        _reserved = logging.LogRecord.__dict__.keys() | {
            "message", "asctime", "args", "exc_info", "exc_text",
            "stack_info", "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in _reserved:
                payload["extra"][key] = value

        # Attach exception traceback if present
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def _build_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setFormatter(_JSONFormatter())
    return handler


def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger configured with JSON output.
    Call once at module level:  logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on repeated imports
    if not logger.handlers:
        logger.addHandler(_build_handler())
        logger.propagate = False

    return logger


def configure_root_logger(level: str = "INFO") -> None:
    """
    Called once at application startup (src/main.py lifespan).
    Sets the root logger level so all child loggers inherit it.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Replace any default handlers with our JSON handler
    if not any(isinstance(h, logging.StreamHandler) and
               isinstance(h.formatter, _JSONFormatter)
               for h in root.handlers):
        root.handlers.clear()
        root.addHandler(_build_handler())
