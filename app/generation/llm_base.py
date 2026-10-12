"""The provider interface, plus the one retry loop every LLM call goes through."""

import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from app.errors import AppError
from app.logging import get_logger, log_event

logger = get_logger(__name__)


class LLMError(Exception):
    """A provider call failed. `retryable` is False for errors a retry cannot fix (bad key, bad request)."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        retry_after: float | None = None,
        rate_limited: bool = False,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after  # seconds the provider asked us to wait, if it said
        self.rate_limited = rate_limited


class LLMTimeout(LLMError):
    pass


class LLMBadResponse(LLMError):
    """The model answered, but not with the JSON we asked for."""


class LLM(ABC):
    name: str
    model: str

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Return the raw text of the model's reply. Raise LLMError on any failure."""


def complete_with_retries[T](
    llm: LLM,
    system: str,
    user: str,
    *,
    parse: Callable[[str], T],
    retries: int = 2,
    backoff_s: float = 1.0,
    retry_after_cap_s: float = 20.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call the LLM and parse its reply. Retry transient failures, then give up with a 503."""
    attempts = retries + 1
    last_error: LLMError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return parse(llm.complete(system, user))
        except LLMError as exc:
            last_error = exc
            log_event(logger, "llm_call_failed", attempt=attempt, error=type(exc).__name__, detail=str(exc))
            if not exc.retryable or attempt == attempts:
                break
            # A quota that resets in many minutes cannot be waited out inside one request: fail now.
            if exc.retry_after is not None and exc.retry_after > retry_after_cap_s:
                break
            wait = backoff_s * 2 ** (attempt - 1)
            if exc.retry_after is not None:
                wait = max(wait, exc.retry_after)
            sleep(wait)
    if last_error is not None and last_error.rate_limited:
        wait_s = max(1, round(last_error.retry_after or retry_after_cap_s))
        minutes = max(1, round(wait_s / 60))
        raise AppError(
            "LLM_RATE_LIMITED",
            f"The language model's usage limit has been reached. Try again in about {minutes} minute(s).",
            503,
            headers={"Retry-After": str(wait_s)},
        ) from last_error
    raise AppError(
        "LLM_UNAVAILABLE",
        f"The language model could not be reached ({type(last_error).__name__}). Please try again.",
        503,
    ) from last_error
