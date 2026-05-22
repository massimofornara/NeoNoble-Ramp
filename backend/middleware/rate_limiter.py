"""
API Rate Limiting & Throttling Middleware.

Sliding window rate limiter with:
- Per-IP rate limiting for anonymous requests
- Per-user rate limiting for authenticated requests
- Configurable limits per route prefix
- 429 Too Many Requests response with Retry-After header
"""

import time
import asyncio
import logging
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Rate limit config: (requests, window_seconds)
RATE_LIMITS: Dict[str, Tuple[int, int]] = {
    "/api/auth/login": (10, 60),          # 10 req/min
    "/api/auth/register": (5, 60),         # 5 req/min
    "/api/neno-exchange/buy": (10, 60),    # 10 req/min (execution-level)
    "/api/neno-exchange/sell": (10, 60),
    "/api/neno-exchange/swap": (10, 60),
    "/api/neno-exchange/offramp": (10, 60),
    "/api/margin/": (60, 60),              # 60 req/min
    "/api/advanced-orders/": (60, 60),
    "/api/kyc/verify-document-ai": (5, 60),# 5 req/min (AI calls)
    "/api/banking/": (20, 60),
    "/api/ws/": (100, 60),
}

DEFAULT_LIMIT = (120, 60)  # 120 req/min default


class SlidingWindowCounter:
    """In-memory sliding window rate limiter."""

    def __init__(self):
        self._windows: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int, int]:
        """Check if request is allowed. Returns (allowed, remaining, retry_after)."""
        async with self._lock:
            now = time.time()
            cutoff = now - window_seconds
            # Remove expired entries
            self._windows[key] = [t for t in self._windows[key] if t > cutoff]
            current_count = len(self._windows[key])

            if current_count >= max_requests:
                retry_after = int(self._windows[key][0] - cutoff) + 1
                return False, 0, retry_after

            self._windows[key].append(now)
            remaining = max_requests - current_count - 1
            return True, remaining, 0

    async def cleanup(self):
        """Remove stale keys (call periodically)."""
        async with self._lock:
            now = time.time()
            stale = [k for k, v in self._windows.items() if not v or v[-1] < now - 300]
            for k in stale:
                del self._windows[k]


_counter = SlidingWindowCounter()


def _get_rate_limit(path: str) -> Tuple[int, int]:
    for prefix, limit in RATE_LIMITS.items():
        if path.startswith(prefix):
            return limit
    return DEFAULT_LIMIT


def _get_client_key(request: Request) -> str:
    # Try to use user_id from auth header if available
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 20:
        # Use token hash as key (first 16 chars)
        return f"user:{auth[7:23]}"
    # Fallback to IP
    client = request.client
    ip = client.host if client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    return f"ip:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip health checks and static assets
        path = request.url.path
        if path in ("/health", "/api/health", "/") or not path.startswith("/api"):
            return await call_next(request)

        # Skip WebSocket upgrades
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # Skip CORS preflight OPTIONS requests
        if request.method == "OPTIONS":
            return await call_next(request)

        max_req, window = _get_rate_limit(path)
        key = f"{_get_client_key(request)}:{path.split('/')[2] if len(path.split('/')) > 2 else 'root'}"

        allowed, remaining, retry_after = await _counter.is_allowed(key, max_req, window)

        if not allowed:
            logger.warning(f"[RATE_LIMIT] Blocked: {key} on {path}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Troppe richieste. Riprova tra poco.", "retry_after": retry_after},
                headers={"Retry-After": str(retry_after), "X-RateLimit-Remaining": "0"},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(max_req)
        return response
