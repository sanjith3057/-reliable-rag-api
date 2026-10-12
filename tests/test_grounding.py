"""Grounding and abstention: the gate, the citation validator, and the model's own refusal."""

from app.generation.providers import FakeLLM
from app.generation.validator import NOT_AVAILABLE, normalise_label, parse_json_object, validate_answer
from tests.conftest import make_client, upload

QUESTION = {"question": "How often must passwords be rotated?"}


def _reply(**overrides) -> dict:
    reply = {"plan": "", "evidence_check": [], "answer": "Every 180 days.", "citations": ["S1"], "answerable": True}
    reply.update(overrides)
    return reply


def _ask(reply: dict):
    llm = FakeLLM([reply])
    client = make_client(llm)
    upload(client)
    return client.post("/ask", json=QUESTION).json(), llm


# ── Retrieval gate ───────────────────────────────────────────────────────────
def test_below_threshold_abstains_without_calling_the_llm():
    llm = FakeLLM()
    client = make_client(llm)
    upload(client)

    body = client.post("/ask", json={"question": "Which country won the football world cup?"}).json()

    assert body == {"answer": NOT_AVAILABLE, "answerable": False, "sources": [], "abstain_reason": "below_threshold"}
    assert llm.calls == [], "the gate must stop the request before the LLM"


# ── Citation validator ───────────────────────────────────────────────────────
def test_hallucinated_citation_is_stripped():
    body, _ = _ask(_reply(citations=["S1", "S99"]))

    assert body["answerable"] is True
    assert len(body["sources"]) == 1
    assert body["sources"][0]["doc_name"] == "security.txt"


def test_answer_with_only_hallucinated_citations_is_refused():
    body, _ = _ask(_reply(citations=["S99", "made_up.pdf"]))

    assert body["answerable"] is False
    assert body["answer"] == NOT_AVAILABLE
    assert body["sources"] == []
    assert body["abstain_reason"] == "no_valid_citations"


def test_answer_with_no_citations_is_refused():
    body, _ = _ask(_reply(citations=[]))
    assert body["answerable"] is False and body["abstain_reason"] == "no_valid_citations"


def test_source_the_model_called_a_distractor_cannot_be_cited():
    reply = _reply(evidence_check=[{"source": "S1", "verdict": "distractor", "note": "wrong year"}])
    body, _ = _ask(reply)
    assert body["answerable"] is False and body["abstain_reason"] == "no_valid_citations"


def test_source_markers_are_removed_from_the_answer_text():
    body, _ = _ask(_reply(answer="Every 180 days [S1]."))
    assert body["answer"] == "Every 180 days."


# ── Model abstention ─────────────────────────────────────────────────────────
def test_model_abstention_is_respected():
    body, _ = _ask(_reply(answer="INSUFFICIENT_CONTEXT", answerable=False, citations=[]))
    assert body["answerable"] is False
    assert body["answer"] == NOT_AVAILABLE
    assert body["abstain_reason"] == "model_abstained"


def test_sentinel_wins_even_if_the_model_claims_answerable():
    body, _ = _ask(_reply(answer="INSUFFICIENT_CONTEXT"))
    assert body["answerable"] is False


def test_reasoning_never_reaches_the_user():
    body, _ = _ask(_reply(plan="SECRET PLAN", evidence_check=[{"source": "S1", "verdict": "supports", "note": "x"}]))
    assert set(body) == {"answer", "answerable", "sources", "abstain_reason"}
    assert "SECRET PLAN" not in str(body)


# ── Validator units ──────────────────────────────────────────────────────────
def test_label_normalisation():
    assert normalise_label("S1") == "S1"
    assert normalise_label("[s2]") == "S2"
    assert normalise_label(3) == "S3"
    assert normalise_label("hr_policy.pdf") is None


def test_json_is_found_inside_code_fences():
    assert parse_json_object('```json\n{"answer": "x", "answerable": true}\n```')["answer"] == "x"


def test_validator_keeps_citation_order_and_drops_duplicates():
    verdict = validate_answer(_reply(citations=["S2", "S1", "S2", "S7"]), {"S1", "S2"})
    assert verdict.citations == ["S2", "S1"]
    assert verdict.dropped_citations == ["S7"]
