"""Failure handling: bad input, bad state, and a misbehaving LLM. Every case must use the one error schema."""

from app.generation.llm_base import LLMError, LLMTimeout
from app.generation.providers import FakeLLM, FallbackLLM
from tests.conftest import assert_error, make_client, upload

QUESTION = {"question": "How often must passwords be rotated?"}
GOOD_REPLY = {"plan": "", "evidence_check": [], "answer": "Every 180 days.", "citations": ["S1"], "answerable": True}


# ── Input failures ───────────────────────────────────────────────────────────
def test_unsupported_file_type(client):
    assert_error(upload(client, "malware.exe", b"MZ..."), 415, "UNSUPPORTED_FILE_TYPE")


def test_empty_file(client):
    assert_error(upload(client, "empty.txt", b""), 422, "EMPTY_FILE")


def test_whitespace_only_file(client):
    assert_error(upload(client, "blank.md", b"   \n\n  "), 422, "NO_TEXT_EXTRACTED")


def test_corrupt_pdf(client):
    assert_error(upload(client, "broken.pdf", b"this is not a pdf at all"), 422, "UNREADABLE_FILE")


def test_binary_data_in_a_text_file(client):
    assert_error(upload(client, "binary.txt", b"\xff\xfe\x00\x81\x8d"), 422, "UNREADABLE_FILE")


def test_oversize_file():
    client = make_client(max_file_mb=1)
    assert_error(upload(client, "big.txt", b"a" * (1024 * 1024 + 1)), 413, "FILE_TOO_LARGE")
    assert client.get("/documents").json()["documents"] == []


def test_missing_file_field(client):
    assert_error(client.post("/ingest"), 422, "VALIDATION_ERROR")


def test_empty_question(client):
    upload(client)
    assert_error(client.post("/ask", json={"question": "   "}), 422, "EMPTY_QUESTION")


def test_question_too_long(client):
    upload(client)
    assert_error(client.post("/ask", json={"question": "a" * 1001}), 422, "QUESTION_TOO_LONG")


def test_missing_question_field(client):
    assert_error(client.post("/ask", json={}), 422, "VALIDATION_ERROR")


def test_malformed_json_body(client):
    response = client.post("/ask", content=b"{not json", headers={"content-type": "application/json"})
    assert_error(response, 422, "VALIDATION_ERROR")


# ── State failures ───────────────────────────────────────────────────────────
def test_ask_with_no_documents(client, llm):
    assert_error(client.post("/ask", json=QUESTION), 409, "NO_DOCUMENTS")
    assert llm.calls == []


def test_unknown_route_and_wrong_method(client):
    assert_error(client.get("/nope"), 404, "NOT_FOUND")
    assert_error(client.get("/ask"), 405, "METHOD_NOT_ALLOWED")


# ── LLM failures ─────────────────────────────────────────────────────────────
def test_llm_timeout_returns_503_after_retries():
    llm = FakeLLM([LLMTimeout("timed out")])
    client = make_client(llm, llm_max_retries=2)
    upload(client)

    assert_error(client.post("/ask", json=QUESTION), 503, "LLM_UNAVAILABLE")
    assert len(llm.calls) == 3, "one attempt plus two retries"


def test_llm_recovers_on_retry():
    llm = FakeLLM([LLMError("HTTP 500"), GOOD_REPLY])
    client = make_client(llm)
    upload(client)

    response = client.post("/ask", json=QUESTION)

    assert response.status_code == 200
    assert response.json()["answer"] == "Every 180 days."
    assert len(llm.calls) == 2


def test_exhausted_quota_fails_fast_with_a_clear_message():
    """A limit that resets in 15 minutes cannot be waited out; say so instead of retrying."""
    llm = FakeLLM([LLMError("HTTP 429 tokens per day", retry_after=881, rate_limited=True)])
    client = make_client(llm)
    upload(client)

    response = client.post("/ask", json=QUESTION)

    assert_error(response, 503, "LLM_RATE_LIMITED")
    assert response.headers["retry-after"] == "881"
    assert "15 minute" in response.json()["error"]["message"]
    assert len(llm.calls) == 1


def test_short_rate_limit_is_waited_out():
    llm = FakeLLM([LLMError("HTTP 429 tokens per minute", retry_after=0, rate_limited=True), GOOD_REPLY])
    client = make_client(llm)
    upload(client)

    assert client.post("/ask", json=QUESTION).status_code == 200
    assert len(llm.calls) == 2


def test_fallback_model_takes_over_while_the_primary_is_rate_limited():
    now = [0.0]
    primary = FakeLLM([LLMError("429", retry_after=600, rate_limited=True), GOOD_REPLY])
    primary.model = "big-model"
    backup = FakeLLM([dict(GOOD_REPLY, answer="From the backup model.")])
    backup.model = "small-model"
    llm = FallbackLLM(primary, backup, clock=lambda: now[0])
    client = make_client(llm)
    upload(client)

    first = client.post("/ask", json=QUESTION).json()
    second = client.post("/ask", json=QUESTION).json()

    assert first["answer"] == second["answer"] == "From the backup model."
    assert len(primary.calls) == 1, "the primary is left alone until its limit resets"
    assert llm.model == "small-model"

    now[0] = 601
    assert llm.model == "big-model"
    assert client.post("/ask", json=QUESTION).json()["answer"] == "Every 180 days."


def test_fallback_is_not_used_for_ordinary_errors():
    primary = FakeLLM([LLMError("HTTP 500")])
    backup = FakeLLM([GOOD_REPLY])
    client = make_client(FallbackLLM(primary, backup))
    upload(client)

    assert_error(client.post("/ask", json=QUESTION), 503, "LLM_UNAVAILABLE")
    assert backup.calls == []


def test_non_retryable_llm_error_fails_fast():
    llm = FakeLLM([LLMError("bad api key", retryable=False)])
    client = make_client(llm)
    upload(client)

    assert_error(client.post("/ask", json=QUESTION), 503, "LLM_UNAVAILABLE")
    assert len(llm.calls) == 1


def test_llm_reply_that_is_not_json_is_retried_then_503():
    llm = FakeLLM(["Sure! The answer is 180 days."])
    client = make_client(llm)
    upload(client)

    assert_error(client.post("/ask", json=QUESTION), 503, "LLM_UNAVAILABLE")
    assert len(llm.calls) == 3


def test_unexpected_exception_is_a_clean_500():
    def explode(system, user):
        raise RuntimeError("boom")

    client = make_client(FakeLLM([explode]))
    upload(client)

    response = client.post("/ask", json=QUESTION)
    assert_error(response, 500, "INTERNAL_ERROR")
    assert "boom" not in response.text, "internal details must not leak"
