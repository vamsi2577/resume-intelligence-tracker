"""
Correlation ID context variable.
Stores a per-request UUID4 in an async-safe ContextVar.
All modules read from here — never pass correlation_id as a function arg.
"""
import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(value: str | None = None) -> str:
    cid = value or str(uuid.uuid4())
    _correlation_id.set(cid)
    return cid
