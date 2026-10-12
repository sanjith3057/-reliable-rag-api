"""Request guards: API key, rate limiting, body size, and input sanitising. No extra dependencies."""

import hmac
import math
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import PurePosixPath

from fastapi import HTTPException, Request

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
    if method == "POST" and path.startswith("/eval"):
        return "eval", settings.rate_limit_eval_per_min
    return "default", settings.rate_limit_default_per_min


def body_limit(path: str, settings: Settings) -> int:
    """Largest request body, in bytes, that a path will accept."""
    if path == "/ingest":
        return settings.max_file_bytes + _MULTIPART_OVERHEAD_BYTES
    return settings.max_json_kb * 1024


def client_ip(request: Request, trusted_proxy_hops: int) -> str:
    """The caller's address. X-Forwarded-For is believed only as far as we have proxies of our own.

    Each proxy appends the address it saw, so with N trusted proxies the real client is the Nth
    entry from the right. Anything further left was supplied by the caller and can be forged.
    """
    direct = request.client.host if request.client else "unknown"
    if trusted_proxy_hops <= 0:
        return direct
    forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
    return forwarded[-trusted_proxy_hops] if len(forwarded) >= trusted_proxy_hops else direct


def _matches(supplied: str, expected: str) -> bool:
    # Constant-time, so the check does not leak how much of a guessed key was right.
    return bool(expected) and hmac.compare_digest(supplied.encode(), expected.encode())


def _is_write(request: Request) -> bool:
    """Anything that changes the library or spends a lot of LLM quota. Asking a question is a read."""
    return request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path != "/ask"


class BodySizeLimit:
    """Stops reading a request body once it passes the limit, whatever Content-Length claimed.

    The declared length is checked earlier, but a client can omit it (chunked upload) or lie.
    This counts the bytes as they arrive, so an oversize body is cut off instead of buffered.
    """

    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = body_limit(scope["path"], self.settings)
        received = 0

        async def counting_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail="Request body is too large")
            return message

        await self.app(scope, counting_receive, send)


def guard_request(request: Request, settings: Settings, limiter: RateLimiter) -> None:
    """Run before every request. Raises AppError to reject it."""
    path = request.url.path
    is_public = path in PUBLIC_PATHS or path.startswith("/static/")

    # 1. Body size, from the declared length, before anything is read or parsed.
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > body_limit(path, settings):
        if path == "/ingest":
            raise AppError("FILE_TOO_LARGE", f"File exceeds the {settings.max_file_mb} MB limit", 413)
        raise AppError("REQUEST_TOO_LARGE", f"Request body exceeds {settings.max_json_kb} KB", 413)

    # 2. API keys. The admin key does everything; the optional read key can only ask and list.
    if (settings.api_key or settings.read_api_key) and not is_public:
        supplied = request.headers.get("x-api-key", "")
        is_admin = _matches(supplied, settings.api_key)
        is_reader = _matches(supplied, settings.read_api_key)
        if not (is_admin or is_reader):
            raise AppError("UNAUTHORIZED", "A valid X-API-Key header is required", 401)
        if _is_write(request) and not is_admin:
            raise AppError("FORBIDDEN", "This key is read-only. This action needs the admin key.", 403)

    # 3. Rate limit, per client and per kind of work.
    if settings.rate_limit_enabled and not is_public:
        bucket, per_minute = _bucket(request, settings)
        client = client_ip(request, settings.trusted_proxy_hops)
        wait = limiter.retry_after(f"{client}:{bucket}", per_minute)
        if wait is not None:
            raise AppError(
                "RATE_LIMITED",
                f"Too many requests. Try again in {wait} seconds.",
                429,
                headers={"Retry-After": str(wait)},
            )
