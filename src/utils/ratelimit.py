"""
Minimal in-memory fixed-window rate limiter (Phase 5 auth-hardening PR2).

Used to throttle the unauthenticated auth endpoints (request-link, verify) so a
single IP can't email-bomb an address or hammer the verify endpoint. Fixed
windows are coarse but cheap and good enough for abuse prevention.

Scope: **single process.** Counters live in this worker's memory, so in a
multi-instance deployment each instance limits independently. That's the point
at which to swap this for a Redis/`limits`-backed store (see the Phase 5 spec);
the call sites won't change.
"""
from __future__ import annotations

import time

from fastapi import Request


class RateLimiter:
    def __init__(self) -> None:
        # key -> (window_start_monotonic, count)
        self._hits: dict[str, tuple[float, int]] = {}

    def hit(self, key: str, limit: int, window_sec: int) -> tuple[bool, int]:
        """Record one hit for `key`. Returns (allowed, retry_after_seconds).

        allowed=False once the count exceeds `limit` within the current window;
        retry_after is the seconds until the window rolls over.
        """
        now = time.monotonic()
        start, count = self._hits.get(key, (now, 0))
        if now - start >= window_sec:
            start, count = now, 0  # window expired → reset
        count += 1
        self._hits[key] = (start, count)

        # Opportunistic prune so the dict can't grow without bound.
        if len(self._hits) > 10_000:
            self._prune(now, window_sec)

        if count > limit:
            return False, max(1, int(window_sec - (now - start)) + 1)
        return True, 0

    def _prune(self, now: float, window_sec: int) -> None:
        for k, (start, _) in list(self._hits.items()):
            if now - start >= window_sec:
                self._hits.pop(k, None)

    def reset(self) -> None:
        self._hits.clear()


# Shared limiter for the auth endpoints.
auth_limiter = RateLimiter()


def client_ip(request: Request) -> str:
    """Best-effort client IP. Behind our own reverse proxy the real client is
    the first hop in X-Forwarded-For; otherwise the socket peer. (We trust XFF
    because the only ingress in front of the app is our proxy.)"""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
