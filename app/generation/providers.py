"""LLM providers. Groq, OpenAI and Gemini all speak the OpenAI chat-completions protocol,
so one small HTTP client covers the three; only the base URL, key and default model differ."""

import json
import re
import time

from app.config import Settings
from app.generation.llm_base import LLM, LLMError, LLMTimeout
from app.logging import get_logger, log_event

logger = get_logger(__name__)

# provider: (base URL, default model, default fallback model, settings field holding the key)
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "groq_api_key"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini", "", "openai_api_key"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash", "", "gemini_api_key"),
}

_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


def _extra_params(model: str, reasoning_effort: str) -> dict:
    """Request fields that only some models accept. Sending them elsewhere is a 400, so be specific.

    The gpt-oss models reason before answering. At their default effort they can spend the whole
    output budget on reasoning and return no JSON; "low" fixes that and uses far fewer tokens.
    """
    if reasoning_effort and "gpt-oss" in model:
        return {"reasoning_effort": reasoning_effort}
    return {}


class OpenAICompatibleLLM(LLM):
    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str,
        timeout_s: float = 30.0,
        reasoning_effort: str = "",
    ):
        self.name = name
        self.model = model
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._extra = _extra_params(model, reasoning_effort)
        self._client = None

    def complete(self, system: str, user: str) -> str:
        import httpx  # lazy: the HTTP client is only needed once a real provider is called

        if not self._api_key:
            raise LLMError(f"No API key configured for provider '{self.name}'", retryable=False)
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_s)
        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    **self._extra,
                },
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeout(f"{self.name} timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name} request failed: {type(exc).__name__}") from exc

        if response.status_code != 200:
            raise LLMError(
                # The provider's own explanation goes to the server log only, never to the client.
                f"{self.name}/{self.model} returned HTTP {response.status_code}: {response.text[:200]}",
                # "json_validate_failed" is the model producing bad JSON, not a bad request: worth a retry.
                retryable=response.status_code in _RETRYABLE_STATUS or "json_validate_failed" in response.text,
                retry_after=_retry_after(response),
                rate_limited=response.status_code == 429,
            )
        try:
            return response.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.name} returned an unexpected payload") from exc


def _retry_after(response) -> float | None:
    try:
        return float(response.headers.get("retry-after", ""))
    except ValueError:
        return None


class FallbackLLM(LLM):
    """Uses the primary model until the provider rate-limits it, then a second model until the limit resets.

    Free tiers cap tokens per minute and per day for each model separately, so a second model
    keeps the service answering when the first one's quota runs out.
    """

    def __init__(self, primary: LLM, fallback: LLM, clock=time.monotonic):
        self.name = primary.name
        self._primary = primary
        self._fallback = fallback
        self._clock = clock
        self._primary_blocked_until = 0.0

    @property
    def model(self) -> str:
        """The model that will take the next call."""
        return self._primary.model if self._clock() >= self._primary_blocked_until else self._fallback.model

    def complete(self, system: str, user: str) -> str:
        if self._clock() >= self._primary_blocked_until:
            try:
                return self._primary.complete(system, user)
            except LLMError as exc:
                if not exc.rate_limited:
                    raise
                self._primary_blocked_until = self._clock() + (exc.retry_after or 60.0)
                log_event(
                    logger, "llm_fallback", primary=self._primary.model, fallback=self._fallback.model, detail=str(exc)
                )
        return self._fallback.complete(system, user)


class FakeLLM(LLM):
    """A stand-in LLM for tests and keyless demos.

    Pass `responses` to script it: each item is used for one call, in order, and the last
    one repeats. An item may be a dict (sent back as JSON), a string (sent back as is), an
    Exception (raised), or a callable taking (system, user). With no script it answers by
    quoting the first sentence of the first source in the prompt and citing that source.
    """

    name = "fake"
    model = "fake-llm"

    def __init__(self, responses: list | None = None):
        self._responses = list(responses) if responses else []
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self._responses:
            return _extractive_reply(system, user)
        item = self._responses[min(len(self.calls), len(self._responses)) - 1]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(system, user)
        return item if isinstance(item, str) else json.dumps(item)


def _extractive_reply(system: str, user: str) -> str:
    if "sub_questions" in system:
        return json.dumps({"sub_questions": []})
    match = re.search(r'<source id="(S\d+)"[^>]*>\n(.*?)\n</source>', user, flags=re.DOTALL)
    if not match:
        return json.dumps(
            {"plan": "", "evidence_check": [], "answer": "INSUFFICIENT_CONTEXT", "citations": [], "answerable": False}
        )
    label, text = match.group(1), match.group(2)
    first_sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    return json.dumps(
        {
            "plan": "Quote the best-ranked source.",
            "evidence_check": [{"source": label, "verdict": "supports", "note": "top-ranked source"}],
            "answer": first_sentence,
            "citations": [label],
            "answerable": True,
        }
    )


def build_llm(settings: Settings) -> LLM:
    provider = settings.llm_provider.lower()
    if provider == "fake":
        return FakeLLM()
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Use one of: fake, {', '.join(PROVIDERS)}")
    base_url, default_model, default_fallback, key_field = PROVIDERS[provider]

    def client(model: str) -> OpenAICompatibleLLM:
        return OpenAICompatibleLLM(
            provider,
            base_url,
            model,
            getattr(settings, key_field),
            settings.llm_timeout_s,
            settings.llm_reasoning_effort,
        )

    model = settings.llm_model or default_model
    # With an explicitly chosen model, only fall back if a fallback was explicitly chosen too.
    fallback = settings.llm_fallback_model or ("" if settings.llm_model else default_fallback)
    if fallback and fallback != model:
        return FallbackLLM(client(model), client(fallback))
    return client(model)
