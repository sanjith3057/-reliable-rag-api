"""Grounding and abstention: the gate, the citation validator, and the model's own refusal."""

from app.generation.providers import FakeLLM
from app.generation.validator import (
    NOT_AVAILABLE,
    normalise_label,
    parse_json_object,
    unsupported_numbers,
    validate_answer,
    wording_is_in_sources,
)
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

    assert body == {
        "answer": NOT_AVAILABLE,
        "answerable": False,
        "sources": [],
        "abstain_reason": "below_threshold",
        "warnings": [],
    }
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
    assert set(body) == {"answer", "answerable", "sources", "abstain_reason", "warnings"}
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


# ── Number check ─────────────────────────────────────────────────────────────
def test_a_figure_that_is_not_in_the_cited_passage_is_flagged():
    body, _ = _ask(_reply(answer="Passwords must be rotated every 999 days."))

    assert body["answerable"] is True, "a warning, not a refusal"
    assert len(body["warnings"]) == 1
    assert "999" in body["warnings"][0]


def test_figures_from_the_passage_raise_no_warning():
    body, _ = _ask(_reply(answer="Every 180 days, and passwords need at least 14 characters."))
    assert body["warnings"] == []


def test_number_check_ignores_formatting_and_the_question():
    assert unsupported_numbers("Up to 20\u202f000\u00a0000 EUR.", "?", ["fines up to 20 000 000 EUR"]) == []
    assert unsupported_numbers("1,200 euros", "?", ["a budget of 1200 euros"]) == []
    assert unsupported_numbers("In 2025 it is 24 days.", "What about 2025?", ["entitled to 24 days"]) == []
    assert unsupported_numbers("It is 8 hours longer.", "?", ["14 hours", "22 hours"]) == ["8"]
    assert unsupported_numbers("No figures here.", "?", ["text"]) == []
    assert unsupported_numbers("4", "?", ["it picks one of four actions"]) == [], "a number word backs its digit"


# ── Wording check ────────────────────────────────────────────────────────────
def test_an_answer_whose_wording_is_not_in_the_cited_passage_is_flagged():
    body, _ = _ask(_reply(answer="Amoxicillin is unsafe."))

    assert body["answerable"] is True, "a warning, not a refusal"
    assert any("do not contain the wording" in warning for warning in body["warnings"])


def test_wording_check_units():
    passage = ["KNOWN ALLERGIES\nPenicillin, shellfish"]
    assert wording_is_in_sources("She is allergic to penicillin.", passage)
    assert not wording_is_in_sources("Amoxicillin is not safe for her.", passage)
    assert not wording_is_in_sources("Canberra", passage)
    assert wording_is_in_sources("Yes.", passage), "a bare yes or no has no wording to check"
    assert wording_is_in_sources("Covered.", ["nothing here", "it is covered by the policy"]), (
        "any cited passage counts"
    )
