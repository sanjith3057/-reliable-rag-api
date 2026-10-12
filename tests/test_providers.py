"""The real HTTP provider, exercised against a fake transport so no network or key is needed."""

import json

import httpx
import pytest

from app.generation.llm_base import LLMError, LLMTimeout
from app.generation.providers import FallbackLLM, OpenAICompatibleLLM, _extra_params, build_llm
from tests.conftest import make_settings


def _llm(handler, model: str = "openai/gpt-oss-20b", **kwargs) -> OpenAICompatibleLLM:
    llm = OpenAICompatibleLLM("groq", "https://llm.test/v1", model, "test-key", **kwargs)
    llm._client = httpx.Client(transport=httpx.MockTransport(handler))
    return llm


def _ok(content: str = '{"answer": "x", "answerable": true}') -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_request_shape_and_reply():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _ok()

    reply = _llm(handler, reasoning_effort="low").complete("system text", "user text")

    assert reply == '{"answer": "x", "answerable": true}'
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["temperature"] == 0
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]
    assert seen["body"]["reasoning_effort"] == "low"


def test_reasoning_effort_is_only_sent_to_models_that_accept_it():
    assert _extra_params("openai/gpt-oss-120b", "low") == {"reasoning_effort": "low"}
    assert _extra_params("gpt-4o-mini", "low") == {}
    assert _extra_params("openai/gpt-oss-20b", "") == {}


def test_missing_key_fails_without_a_network_call():
    llm = OpenAICompatibleLLM("groq", "https://llm.test/v1", "m", api_key="")
    with pytest.raises(LLMError) as raised:
        llm.complete("s", "u")
    assert raised.value.retryable is False


def test_rate_limit_is_flagged_with_the_providers_wait():
    llm = _llm(lambda request: httpx.Response(429, headers={"retry-after": "881"}, text="tokens per day"))
    with pytest.raises(LLMError) as raised:
        llm.complete("s", "u")
    assert raised.value.rate_limited is True
    assert raised.value.retry_after == 881
    assert raised.value.retryable is True


def test_bad_json_from_the_model_is_retryable_but_a_bad_request_is_not():
    bad_json = _llm(lambda request: httpx.Response(400, text='{"error":{"code":"json_validate_failed"}}'))
    bad_request = _llm(lambda request: httpx.Response(400, text='{"error":{"code":"invalid_model"}}'))

    with pytest.raises(LLMError) as first:
        bad_json.complete("s", "u")
    with pytest.raises(LLMError) as second:
        bad_request.complete("s", "u")

    assert first.value.retryable is True
    assert second.value.retryable is False


def test_auth_failure_is_not_retried_and_the_key_is_not_in_the_error():
    llm = _llm(lambda request: httpx.Response(401, text="invalid api key"))
    with pytest.raises(LLMError) as raised:
        llm.complete("s", "u")
    assert raised.value.retryable is False
    assert "test-key" not in str(raised.value)


def test_timeout_becomes_llm_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMTimeout):
        _llm(handler).complete("s", "u")


def test_unexpected_payload_is_an_llm_error():
    with pytest.raises(LLMError):
        _llm(lambda request: httpx.Response(200, json={"unexpected": True})).complete("s", "u")


def test_groq_gets_a_fallback_model_by_default():
    llm = build_llm(make_settings(llm_provider="groq", groq_api_key="k"))
    assert isinstance(llm, FallbackLLM)
    assert llm.model == "openai/gpt-oss-120b"


def test_an_explicit_model_has_no_implicit_fallback():
    llm = build_llm(make_settings(llm_provider="groq", groq_api_key="k", llm_model="openai/gpt-oss-20b"))
    assert isinstance(llm, OpenAICompatibleLLM)
    assert llm.model == "openai/gpt-oss-20b"


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        build_llm(make_settings(llm_provider="nope"))
