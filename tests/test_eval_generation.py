"""Evaluating on any documents: generated question sets, the LLM judge, and report persistence."""

from app.evaluation.evaluator import load_report, run_evaluation, save_report
from app.evaluation.generator import GENERAL_KNOWLEDGE_TRAPS, generate_questions
from app.generation.llm_base import LLMError
from app.generation.providers import FakeLLM
from tests.conftest import assert_error, make_client, make_service

HANDBOOK = (
    b"Security handbook. Passwords must be at least 14 characters long and must be rotated every 180 days. "
    b"Multi-factor authentication is mandatory for all company accounts, with no exceptions for any team. "
    b"Suspected incidents must be reported within 4 hours of discovery to the security team by email."
)
GOOD_DRAFT = {
    "question": "How often must passwords be rotated?",
    "answer_keyword": "180 days",
    "evidence": "must be rotated every 180 days",
}
ANSWER = {"plan": "", "evidence_check": [], "answer": "Every 180 days.", "citations": ["S1"], "answerable": True}


def _scripted(draft=GOOD_DRAFT, verdict=None):
    """A FakeLLM that plays the question writer, the answerer and (optionally) the judge."""

    def reply(system, user):
        if "test questions" in system:
            return draft
        if "strict grader" in system:
            if isinstance(verdict, Exception):
                raise verdict
            return verdict
        if "sub_questions" in system:
            return {"sub_questions": []}
        return ANSWER

    return FakeLLM([reply])


# ── Generated question sets ──────────────────────────────────────────────────
def test_questions_are_written_from_the_library_with_verified_gold_labels():
    service = make_service(_scripted())
    service.ingest("handbook.txt", HANDBOOK)

    generated = generate_questions(service, n=3, seed=1)

    written = [q for q in generated.questions if q.expected_answerable]
    assert len(written) == 1, "one passage in the library, so one question"
    assert written[0].expected_sources == ["handbook.txt"]
    assert written[0].expected_keywords == ["180 days"]
    assert written[0].expected_evidence == ["must be rotated every 180 days"]
    assert generated.skipped == 0


def test_general_knowledge_traps_are_always_added():
    service = make_service(_scripted())
    service.ingest("handbook.txt", HANDBOOK)

    traps = [q for q in generate_questions(service, n=1).questions if not q.expected_answerable]

    assert [q.question for q in traps] == GENERAL_KNOWLEDGE_TRAPS
    assert all(q.type == "unanswerable" for q in traps)


def test_a_draft_whose_evidence_is_not_in_the_passage_is_discarded():
    """If the model paraphrased instead of copying, the gold label would be wrong, so drop the draft."""
    invented = dict(GOOD_DRAFT, evidence="passwords expire after half a year")
    service = make_service(_scripted(invented))
    service.ingest("handbook.txt", HANDBOOK)

    generated = generate_questions(service, n=1)

    assert generated.skipped == 1
    assert all(not q.expected_answerable for q in generated.questions)


def test_a_sentence_long_keyword_is_discarded():
    """A correct answer rarely repeats a whole sentence, so such a keyword would fail good answers."""
    wordy = dict(GOOD_DRAFT, answer_keyword="must be rotated every 180 days")
    service = make_service(_scripted(wordy))
    service.ingest("handbook.txt", HANDBOOK)
    assert generate_questions(service, n=1).skipped == 1


def test_overlapping_passages_do_not_produce_the_same_question_twice():
    service = make_service(_scripted(), chunk_size=260, chunk_overlap=120)
    service.ingest("handbook.txt", HANDBOOK * 2)

    generated = generate_questions(service, n=5, seed=3)

    written = [q for q in generated.questions if q.expected_answerable]
    assert len(written) == 1 and generated.skipped >= 1


def test_a_passage_with_no_clear_fact_is_skipped():
    service = make_service(_scripted({"question": ""}))
    service.ingest("handbook.txt", HANDBOOK)
    assert generate_questions(service, n=1).skipped == 1


def test_generation_needs_documents(client):
    assert_error(client.post("/eval/generate"), 409, "NO_DOCUMENTS")


def test_generate_then_evaluate_end_to_end():
    client = make_client(_scripted())
    client.post("/ingest", files={"file": ("handbook.txt", HANDBOOK)})

    generated = client.post("/eval/generate", json={"n": 2, "seed": 7})
    assert generated.status_code == 200
    report = client.post("/eval", json={"questions": generated.json()["questions"]}).json()

    assert report["dataset"] == "custom"
    assert report["summary"]["total"] == 4
    by_id = {r["id"]: r for r in report["results"]}
    assert by_id["gen01"]["passed"] is True and by_id["gen01"]["retrieval_hit"] is True
    assert all(by_id[f"trap{i}"]["passed"] for i in (1, 2, 3)), "off-topic questions must be refused"


def test_generate_request_limits(client):
    assert_error(client.post("/eval/generate", json={"n": 0}), 422, "VALIDATION_ERROR")
    assert_error(client.post("/eval/generate", json={"n": 16}), 422, "VALIDATION_ERROR")


# ── LLM judge ────────────────────────────────────────────────────────────────
QUESTION = {
    "id": "q1",
    "question": "How often must passwords be rotated?",
    "expected_answerable": True,
    "expected_sources": ["handbook.txt"],
    "expected_keywords": ["180"],
}


def _judged_report(verdict, judge=True):
    client = make_client(_scripted(verdict=verdict))
    client.post("/ingest", files={"file": ("handbook.txt", HANDBOOK)})
    return client.post("/eval", json={"questions": [QUESTION], "judge": judge}).json()


def test_judge_scores_faithfulness_and_relevance():
    report = _judged_report({"faithful": True, "relevant": True, "unsupported": []})

    assert report["config"]["judge"] is True
    assert report["results"][0]["faithful"] is True
    assert report["summary"]["faithfulness"] == 1.0
    assert report["summary"]["answer_relevance"] == 1.0


def test_judge_can_fail_an_answer_that_passed_the_keyword_check():
    report = _judged_report({"faithful": False, "relevant": True, "unsupported": ["the figure"]})

    assert report["results"][0]["keywords_ok"] is True
    assert report["results"][0]["faithful"] is False
    assert report["summary"]["faithfulness"] == 0.0


def test_judge_is_off_by_default_and_costs_nothing():
    report = _judged_report({"faithful": True, "relevant": True}, judge=False)
    assert report["summary"]["faithfulness"] is None
    assert report["results"][0]["faithful"] is None


def test_a_failed_judge_call_leaves_the_question_unjudged_not_failed():
    report = _judged_report(LLMError("judge is down", retryable=False))

    assert report["results"][0]["passed"] is True
    assert report["results"][0]["faithful"] is None
    assert report["summary"]["faithfulness"] is None


# ── Report persistence ───────────────────────────────────────────────────────
def test_latest_report_survives_a_restart(tmp_path):
    service = make_service(_scripted())
    service.ingest("handbook.txt", HANDBOOK)
    report = run_evaluation(service, generate_questions(service, n=1).questions)
    path = tmp_path / "store" / "latest_eval.json"

    save_report(path, report)

    assert load_report(path) == report


def test_missing_or_corrupt_report_is_treated_as_no_report(tmp_path):
    assert load_report(None) is None
    assert load_report(tmp_path / "absent.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_report(broken) is None
    save_report(None, None)  # nowhere to write: a no-op, not an error
