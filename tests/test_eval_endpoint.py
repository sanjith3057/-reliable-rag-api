import pytest

from app.evaluation.evaluator import render_markdown
from app.evaluation.metrics import (
    evidence_found,
    evidence_ranks,
    keywords_match,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    score_question,
    summarise,
)
from app.generation.llm_base import LLMTimeout
from app.generation.providers import FakeLLM
from app.schemas import EvalQuestion, EvalReport
from tests.conftest import assert_error, make_client, upload

SUMMARY_KEYS = {
    "total",
    "passed",
    "retrieval_hit_at_k",
    "abstention_accuracy",
    "citation_correctness",
    "answer_keyword_accuracy",
    "distractor_resilience",
    "avg_latency_ms",
}

ANSWERABLE = {
    "id": "q1",
    "question": "How often must passwords be rotated?",
    "expected_answerable": True,
    "expected_sources": ["security.txt"],
    "expected_keywords": ["180||14"],
}
UNANSWERABLE = {
    "id": "q2",
    "type": "unanswerable",
    "question": "Which country won the football world cup?",
    "expected_answerable": False,
}


def test_eval_returns_all_metric_keys(client):
    upload(client)
    response = client.post("/eval", json={"questions": [ANSWERABLE, UNANSWERABLE]})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"run_id", "dataset", "config", "summary", "results"}
    assert set(body["summary"]) == SUMMARY_KEYS
    assert body["summary"]["total"] == 2
    assert [r["id"] for r in body["results"]] == ["q1", "q2"]
    assert all(r["latency_ms"] >= 0 for r in body["results"])


def test_abstention_is_scored_correctly(client):
    upload(client)
    wrong = dict(UNANSWERABLE, id="q3", question="How often must passwords be rotated?")  # system will answer this

    body = client.post("/eval", json={"questions": [ANSWERABLE, UNANSWERABLE, wrong]}).json()

    by_id = {r["id"]: r for r in body["results"]}
    assert by_id["q1"]["passed"] is True and by_id["q1"]["answerable"] is True
    assert by_id["q2"]["passed"] is True and by_id["q2"]["answerable"] is False
    assert by_id["q3"]["passed"] is False, "answering a question marked unanswerable must fail"
    assert body["summary"]["abstention_accuracy"] == round(2 / 3, 3)
    assert body["summary"]["passed"] == 2


def test_empty_question_list_is_rejected(client):
    upload(client)
    assert_error(client.post("/eval", json={"questions": []}), 422, "EMPTY_QUESTION_LIST")


def test_more_than_50_questions_is_rejected(client):
    upload(client)
    questions = [dict(ANSWERABLE, id=f"q{i}") for i in range(51)]
    assert_error(client.post("/eval", json={"questions": questions}), 422, "TOO_MANY_QUESTIONS")


def test_eval_with_no_documents(client):
    assert_error(client.post("/eval", json={"questions": [ANSWERABLE]}), 409, "NO_DOCUMENTS")


def test_eval_refuses_to_run_without_the_documents_it_was_written_for(client):
    upload(client, "unrelated.txt", b"The cafeteria opens at 08:00 on weekdays.")

    response = client.post("/eval")  # the default set needs the sample documents

    assert_error(response, 409, "EVAL_DOCUMENTS_MISSING")
    assert "hr_policy_2025.md" in response.json()["error"]["message"] or "expense_policy.pdf" in response.text
    assert_error(client.get("/eval/latest"), 404, "NO_EVAL_RUN")


def test_default_eval_set_runs_and_latest_is_stored(client):
    assert_error(client.get("/eval/latest"), 404, "NO_EVAL_RUN")
    client.post("/ingest/samples")

    report = client.post("/eval").json()

    assert report["dataset"] == "test"
    assert report["summary"]["total"] >= 15
    assert client.get("/eval/latest").json()["run_id"] == report["run_id"]


def test_a_rate_limited_question_is_retried_before_being_scored():
    good = {"plan": "", "evidence_check": [], "answer": "Every 180 days.", "citations": ["S1"], "answerable": True}
    # The first attempt uses up its three LLM tries; the evaluator pauses and asks again.
    client = make_client(FakeLLM([LLMTimeout("429"), LLMTimeout("429"), LLMTimeout("429"), good]))
    upload(client)

    body = client.post("/eval", json={"questions": [ANSWERABLE]}).json()

    assert body["results"][0]["error"] is None
    assert body["results"][0]["passed"] is True


def test_an_llm_outage_fails_the_question_not_the_run():
    client = make_client(FakeLLM([LLMTimeout("down")]))
    upload(client)

    body = client.post("/eval", json={"questions": [ANSWERABLE, UNANSWERABLE]}).json()

    by_id = {r["id"]: r for r in body["results"]}
    assert by_id["q1"]["error"] == "LLM_UNAVAILABLE" and by_id["q1"]["passed"] is False
    assert by_id["q2"]["passed"] is True, "the gate needs no LLM, so this one still works"
    assert body["summary"]["abstention_accuracy"] == 0.5


# ── Metric units ─────────────────────────────────────────────────────────────
def test_keyword_alternatives():
    assert keywords_match("It lasts six months.", ["6 months||six months"])
    assert keywords_match("18 days then 24 days", ["18", "24"])
    assert not keywords_match("18 days", ["18", "24"])


def test_keywords_ignore_typographic_spaces_and_hyphens():
    assert keywords_match("up to 10 000 000 EUR", ["10 000 000"])
    assert keywords_match("a machine‑readable format", ["machine-readable"])


def _question(**overrides) -> EvalQuestion:
    values = {
        "id": "x",
        "question": "?",
        "type": "distractor",
        "expected_answerable": True,
        "expected_sources": ["2025.md"],
        "expected_keywords": ["24"],
        "distractor_sources": ["2024.md"],
    }
    values.update(overrides)
    return EvalQuestion(**values)


def test_citing_the_distractor_fails_distractor_resilience():
    good = score_question(
        _question(),
        answerable=True,
        answer="24 days",
        retrieved=["2025.md", "2024.md"],
        cited=["2025.md"],
        latency_ms=1,
    )
    bad = score_question(
        _question(),
        answerable=True,
        answer="24 days",
        retrieved=["2025.md", "2024.md"],
        cited=["2025.md", "2024.md"],
        latency_ms=1,
    )

    assert good.passed and good.distractor_ok and good.citation_ok and good.retrieval_hit
    assert bad.distractor_ok is False and bad.citation_ok is False and not bad.passed


def test_retrieval_hit_needs_every_expected_source():
    question = _question(type="multi", expected_sources=["a.md", "b.md"], distractor_sources=[], expected_keywords=[])
    result = score_question(question, answerable=True, answer="x", retrieved=["a.md"], cited=["a.md"], latency_ms=1)
    assert result.retrieval_hit is False


def test_retrieval_hit_needs_the_supporting_passage_not_just_the_right_file():
    """On a long document the right file is always retrieved, so the check must look inside the chunks."""
    question = _question(type="answerable", expected_evidence=["72 hours"], distractor_sources=[], expected_keywords=[])
    common = {"answerable": True, "answer": "x", "retrieved": ["2025.md"], "cited": ["2025.md"], "latency_ms": 1}

    found = score_question(question, retrieved_texts=["notify within 72\nhours of becoming aware"], **common)
    missed = score_question(question, retrieved_texts=["a passage about something else"], **common)

    assert found.retrieval_hit is True, "matching ignores line breaks and case"
    assert missed.retrieval_hit is False


def test_evidence_found_needs_every_item():
    assert evidence_found(["10 000 000", "20 000 000"], ["up to 10 000 000 EUR", "up to 20 000 000 EUR"])
    assert not evidence_found(["10 000 000", "20 000 000"], ["up to 10 000 000 EUR"])
    assert evidence_found([], [])


def test_ranked_retrieval_metrics():
    ranked = ["nothing useful", "notify within 72 hours", "filler", "fines up to 20 000 000 EUR"]
    ranks = evidence_ranks(["72 hours", "20 000 000", "not in any chunk"], ranked)

    assert ranks == [2, 4, None]
    assert recall_at_k(ranks, 3) == pytest.approx(1 / 3)
    assert recall_at_k(ranks, 5) == pytest.approx(2 / 3)
    assert reciprocal_rank(ranks) == 0.5
    assert reciprocal_rank([None]) == 0.0


def test_ndcg_rewards_a_higher_rank():
    assert ndcg_at_k([1], 5) == 1.0
    assert ndcg_at_k([1], 5) > ndcg_at_k([3], 5) > ndcg_at_k([5], 5) > 0
    assert ndcg_at_k([6], 5) == 0.0, "outside the cut-off counts for nothing"
    assert ndcg_at_k([1, 2], 5) == 1.0
    assert ndcg_at_k([1, None], 5) < 1.0


def test_summary_and_markdown_render():
    results = [
        score_question(
            _question(), answerable=True, answer="24", retrieved=["2025.md"], cited=["2025.md"], latency_ms=10
        ),
        score_question(
            _question(
                id="y",
                type="unanswerable",
                expected_answerable=False,
                expected_sources=[],
                expected_keywords=[],
                distractor_sources=[],
            ),
            answerable=False,
            answer="n/a",
            retrieved=[],
            cited=[],
            latency_ms=30,
        ),
    ]
    summary = summarise(results)
    assert summary.passed == 2 and summary.abstention_accuracy == 1.0 and summary.avg_latency_ms == 20.0

    report = EvalReport(run_id="r", dataset="test", config={"top_k": 5}, summary=summary, results=results)
    markdown = render_markdown(report)
    assert "| Abstention accuracy | 100% |" in markdown
    assert "| x | distractor | yes |" in markdown
