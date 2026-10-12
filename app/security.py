"""Request guards: API key, rate limiting, body size, and input sanitising. No extra dependencies."""

import hmac
import math
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import PurePosixPath

from fastapi import Request

from app.config import Settings
from app.errors import AppError

# Reachable without an API key: the UI shell, liveness, and the API docs.
PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
# Only for our own pages. /docs loads Swagger UI from a CDN, which this policy would block.
UI_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)

_MULTIPART_OVERHEAD_BYTES = 64 * 1024


def sanitize_filename(filename: str) -> str:
    """Reduce an uploaded filename to a safe display name.

    The name is stored, shown in the UI and written into the LLM prompt, so it must not
    carry a path, control characters, or markup that could pose as part of the prompt.
    """
    name = PurePosixPath((filename or "").replace("\\", "/")).name
    name = re.sub(r"[^\w.\- ()]", "_", name).strip(" .")
    stem, dot, extension = name.rpartition(".")
    return f"{stem[:100]}{dot}{extension[:10]}" if dot else name[:100]


def sanitize_request_id(value: str | None) -> str | None:
    """Accept a caller-supplied request ID only if it is short and plain, so it cannot pollute logs."""
    return value if value and re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", value) else None


class RateLimiter:
    """Sliding-window limiter held in memory: at most `limit` requests per `window_s` for each key.

    Good for one process. Several workers or replicas would each keep their own count, so a
    multi-instance deployment needs a shared store such as Redis.
    """

    def __init__(self, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str, limit: int) -> int | None:
        """Record a request. Return None if it is allowed, or the seconds to wait if it is not."""
        now = self._clock()
        with self._lock:
            if len(self._hits) > 10_000:
                self._forget_idle(now)
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= limit:
                return max(1, math.ceil(self.window_s - (now - hits[0])))
            hits.append(now)
            return None

    def _forget_idle(self, now: float) -> None:
        for key in [k for k, hits in self._hits.items() if not hits or now - hits[-1] >= self.window_s]:
            del self._hits[key]


def _bucket(request: Request, settings: Settings) -> tuple[str, int]:
    path, method = request.url.path, request.method
    if method == "POST" and path == "/ask":
        return "ask", settings.rate_limit_ask_per_min
    if method == "POST" and path.startswith("/ingest"):
        return "ingest", settings.rate_limit_ingest_per_min
    if method == "POST" and path == "/eval":
        return "eval", settings.rate_limit_eval_per_min
    return "default", settings.rate_limit_default_per_min


def guard_request(request: Request, settings: Settings, limiter: RateLimiter) -> None:
    """Run before every request. Raises AppError to reject it."""
    path = request.url.path
    is_public = path in PUBLIC_PATHS or path.startswith("/static/")

    # 1. Body size, from the declared length, before anything is read or parsed.
    is_upload = path == "/ingest"
    limit = settings.max_file_bytes + _MULTIPART_OVERHEAD_BYTES if is_upload else settings.max_json_kb * 1024
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        if is_upload:
            raise AppError("FILE_TOO_LARGE", f"File exceeds the {settings.max_file_mb} MB limit", 413)
        raise AppError("REQUEST_TOO_LARGE", f"Request body exceeds {settings.max_json_kb} KB", 413)

    # 2. API key, compared in constant time so the check does not leak how much of a guess was right.
    supplied = request.headers.get("x-api-key", "")
    if settings.api_key and not is_public:
        if not hmac.compare_digest(supplied.encode(), settings.api_key.encode()):
            raise AppError("UNAUTHORIZED", "A valid X-API-Key header is required", 401)

    # 3. Rate limit, per client and per kind of work. The proxy-supplied X-Forwarded-For header is
    #    deliberately not trusted, since any caller can set it to dodge the limit.
    if settings.rate_limit_enabled and not is_public:
        bucket, per_minute = _bucket(request, settings)
        client = request.client.host if request.client else "unknown"
        wait = limiter.retry_after(f"{client}:{bucket}", per_minute)
        if wait is not None:
            raise AppError(
                "RATE_LIMITED",
                f"Too many requests. Try again in {wait} seconds.",
                429,
                headers={"Retry-After": str(wait)},
            )
