"""In-process fixed-window rate limiting.

State is per-process: with `uvicorn --workers N` the effective limit is up to
N x the configured one, and counters reset on restart. Good enough to blunt
brute-force and spam at this scale without Redis.
"""

import time
from collections.abc import Awaitable, Callable

from fastapi import Request

from app.config import settings
from app.errors import AppError


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def rate_limit(
    name: str, limit: int, window_seconds: int
) -> Callable[[Request], Awaitable[None]]:
    windows: dict[str, tuple[float, int]] = {}

    async def dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        now = time.monotonic()
        key = _client_ip(request)
        expired = [k for k, (start, _) in windows.items() if now - start >= window_seconds]
        for k in expired:
            del windows[k]
        start, count = windows.get(key, (now, 0))
        if count >= limit:
            raise AppError(429, "rate_limited", "Too many requests. Please try again shortly.")
        windows[key] = (start, count + 1)

    dependency.__name__ = f"rate_limit_{name}"
    return dependency
