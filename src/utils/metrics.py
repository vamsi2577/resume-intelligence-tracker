"""
In-memory metrics store.

KPIs tracked:
  - Request latency (per endpoint+method)
  - API success / failure rates (4xx/5xx)
  - Parse failure rate (422 count)
  - DB query latency (per operation)

Thread-safe via threading.Lock (no external deps).
All durations in milliseconds.
"""
from __future__ import annotations

import functools
import time
import threading
from collections import defaultdict, deque
from typing import Any, Callable, Deque

from src.utils.logger import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()

# Rolling-window size for latency samples. Bounded so a long-running
# process can't grow these lists without limit (one append per request /
# DB call would otherwise leak memory until restart). Aggregate counters
# (_status_counts, _parse_failures) stay exact; only the latency *sample*
# window is capped — p95/avg are computed over the most recent N.
_MAX_SAMPLES = 1000

# ── Internal state ────────────────────────────────────────

_request_latencies: dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=_MAX_SAMPLES))  # key: "METHOD /path"
_status_counts: dict[str, int] = defaultdict(int)                 # key: "2xx" / "4xx" / "5xx"
_parse_failures: dict[str, int] = defaultdict(int)                # key: endpoint
_db_latencies: dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=_MAX_SAMPLES))        # key: operation name


# ── Public recorders ──────────────────────────────────────

def record_request(endpoint: str, method: str, status_code: int, duration_ms: float) -> None:
    key = f"{method.upper()} {endpoint}"
    bucket = f"{status_code // 100}xx"
    with _lock:
        _request_latencies[key].append(max(duration_ms, 0.0))
        _status_counts[bucket] += 1
    logger.debug(
        "Request recorded",
        extra={"endpoint": endpoint, "method": method,
               "status_code": status_code, "duration_ms": round(duration_ms, 2)},
    )


def record_parse_failure(endpoint: str) -> None:
    with _lock:
        _parse_failures[endpoint] += 1
    logger.debug("Parse failure recorded", extra={"endpoint": endpoint})


def record_db_query(operation: str, duration_ms: float) -> None:
    with _lock:
        _db_latencies[operation].append(max(duration_ms, 0.0))
    logger.debug(
        "DB query recorded",
        extra={"operation": operation, "duration_ms": round(duration_ms, 2)},
    )


# ── Snapshot ──────────────────────────────────────────────

def get_snapshot() -> dict[str, Any]:
    with _lock:
        req_stats = {
            key: _latency_stats(vals)
            for key, vals in _request_latencies.items()
        }
        db_stats = {
            op: _latency_stats(vals)
            for op, vals in _db_latencies.items()
        }
        total_requests = sum(_status_counts.values())
        failure_count = _status_counts.get("4xx", 0) + _status_counts.get("5xx", 0)
        parse_total = sum(_parse_failures.values())

        return {
            "requests": {
                "total": total_requests,
                "by_status": dict(_status_counts),
                "success_rate": round((total_requests - failure_count) / total_requests, 4)
                               if total_requests else 1.0,
                "failure_rate": round(failure_count / total_requests, 4)
                               if total_requests else 0.0,
                "latency_ms": req_stats,
            },
            "parse_failures": {
                "total": parse_total,
                "by_endpoint": dict(_parse_failures),
            },
            "db_queries": {
                "latency_ms": db_stats,
            },
        }


def reset() -> None:
    """Reset all metrics — used in tests."""
    with _lock:
        _request_latencies.clear()
        _status_counts.clear()
        _parse_failures.clear()
        _db_latencies.clear()


# ── Helpers ───────────────────────────────────────────────

def _latency_stats(values: "Deque[float] | list[float]") -> dict[str, float]:
    if not values:
        return {"count": 0, "min": 0.0, "max": 0.0, "avg": 0.0, "p95": 0.0}
    sorted_vals = sorted(values)
    count = len(sorted_vals)
    p95_idx = max(0, int(count * 0.95) - 1)
    return {
        "count": count,
        "min": round(sorted_vals[0], 2),
        "max": round(sorted_vals[-1], 2),
        "avg": round(sum(sorted_vals) / count, 2),
        "p95": round(sorted_vals[p95_idx], 2),
    }


# ── DB query decorator ────────────────────────────────────

def track_db_query(operation: str) -> Callable:
    """Decorator for async service functions — records DB query latency."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                record_db_query(operation, duration_ms)
        return wrapper
    return decorator
