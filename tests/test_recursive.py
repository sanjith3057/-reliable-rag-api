from app.domain import Chunk, ScoredChunk
from app.generation.llm_base import LLMError
from app.generation.prompt import position_aware_order
from app.generation.providers import FakeLLM
from app.retrieval.retriever import RecursiveRetriever, dedupe
from tests.conftest import make_service


def _scored(chunk_id: str, score: float) -> ScoredChunk:
    return ScoredChunk(Chunk(chunk_id, "d", "d.txt", None, 0, f"text of {chunk_id}"), score)


class StubRetriever:
    """Returns a fixed result per query and records what was asked."""

    def __init__(self, results: dict[str, list[ScoredChunk]], default: list[ScoredChunk]):
        self.results = results
        self.default = default
        self.queries: list[str] = []

    def retrieve(self, query: str, k: int) -> list[ScoredChunk]:
        self.queries.append(query)
        return self.results.get(query, self.default)[:k]


def _recursive(stub, decompose, **kwargs):
    options = {"gate": 0.4, "sufficiency": 0.7, "max_depth": 2, "max_sub_questions": 3}
    options.update(kwargs)
    return RecursiveRetriever(stub, decompose, **options)


def test_strong_evidence_does_not_recurse():
    stub = StubRetriever({}, [_scored("a", 0.9)])
    calls = []
    chunks, trace = _recursive(stub, lambda q: calls.append(q) or ["x"]).retrieve("q", 5)

    assert [c.chunk.chunk_id for c in chunks] == ["a"]
    assert calls == [] and trace.depth_reached == 0 and trace.retrievals == 1


def test_evidence_below_the_gate_does_not_recurse():
    stub = StubRetriever({}, [_scored("a", 0.2)])
    calls = []
    _, trace = _recursive(stub, lambda q: calls.append(q) or ["x"]).retrieve("q", 5)

    assert calls == [], "no LLM call for a question the documents clearly do not cover"
    assert trace.top_similarity == 0.2


def test_middling_evidence_is_decomposed_and_merged():
    stub = StubRetriever(
        {"q": [_scored("a", 0.5)], "sub one": [_scored("b", 0.9)], "sub two": [_scored("c", 0.8)]},
        default=[],
    )
    chunks, trace = _recursive(stub, lambda q: ["sub one", "sub two"]).retrieve("q", 5)

    assert [c.chunk.chunk_id for c in chunks] == ["b", "c", "a"]
    assert trace.sub_questions == ["sub one", "sub two"]
    assert trace.top_similarity == 0.5, "the gate is judged on the original question"
    assert trace.depth_reached == 1


def test_depth_cap_is_respected():
    stub = StubRetriever({}, [_scored("a", 0.5)])  # always middling, so it would recurse forever
    _, trace = _recursive(stub, lambda q: [q + "+"], max_depth=2).retrieve("q", 5)

    assert trace.depth_reached == 2
    assert stub.queries == ["q", "q+", "q++"]


def test_sub_question_count_is_capped():
    stub = StubRetriever({}, [_scored("a", 0.5)])
    _recursive(stub, lambda q: [f"s{i}" for i in range(10)], max_depth=1, max_sub_questions=3).retrieve("q", 5)
    assert len(stub.queries) == 1 + 3


def test_recursion_returns_no_duplicate_chunks():
    stub = StubRetriever({"q": [_scored("a", 0.5), _scored("b", 0.45)]}, default=[_scored("a", 0.6), _scored("b", 0.3)])
    chunks, _ = _recursive(stub, lambda q: ["s1", "s2"], max_depth=1).retrieve("q", 5)

    ids = [c.chunk.chunk_id for c in chunks]
    assert ids == ["a", "b"]
    assert [c.score for c in chunks] == [0.6, 0.45], "each chunk keeps its best score"


def test_dedupe_keeps_best_score_sorted():
    result = dedupe([_scored("a", 0.2), _scored("b", 0.9), _scored("a", 0.7)])
    assert [(c.chunk.chunk_id, c.score) for c in result] == [("b", 0.9), ("a", 0.7)]


def test_failed_decomposition_falls_back_to_first_pass_evidence():
    answer = {"plan": "", "evidence_check": [], "answer": "180 days.", "citations": ["S1"], "answerable": True}

    def reply(system, user):
        if "sub_questions" in system:
            raise LLMError("decompose is down", retryable=False)
        return answer

    llm = FakeLLM([reply])
    service = make_service(llm, similarity_threshold=0.05, sufficiency_threshold=0.99)
    service.ingest("security.txt", b"Passwords must be rotated every 180 days.")

    outcome = service.ask("How often must passwords be rotated?")

    assert outcome.response.answerable is True
    assert outcome.trace.sub_questions == []


ABSTAIN = {"plan": "", "evidence_check": [], "answer": "INSUFFICIENT_CONTEXT", "citations": [], "answerable": False}
TWO_FACTS = b"Passwords must be rotated every 180 days.\n\nThe home office allowance is 350 euros."
TWO_PART_QUESTION = "How often must passwords be rotated, and how much is the home office allowance?"


def test_abstention_on_a_multi_part_question_gets_a_second_pass():
    answers = iter([ABSTAIN, {**ABSTAIN, "answer": "180 days; 350 euros.", "citations": ["S1"], "answerable": True}])

    def reply(system, user):
        if "sub_questions" in system:
            return {"sub_questions": ["How often must passwords be rotated?", "How much is the home office allowance?"]}
        return next(answers)

    llm = FakeLLM([reply])
    service = make_service(llm)
    service.ingest("policy.txt", TWO_FACTS)

    outcome = service.ask(TWO_PART_QUESTION)

    assert outcome.response.answerable is True
    assert outcome.response.answer == "180 days; 350 euros."
    assert len(outcome.trace.sub_questions) == 2
    assert len(llm.calls) == 3, "answer, decompose, answer again"


def test_abstention_on_a_single_fact_question_stays_an_abstention():
    def reply(system, user):
        return {"sub_questions": []} if "sub_questions" in system else ABSTAIN

    llm = FakeLLM([reply])
    service = make_service(llm)
    service.ingest("policy.txt", TWO_FACTS)

    outcome = service.ask("How often must passwords be rotated?")

    assert outcome.response.answerable is False
    assert outcome.response.abstain_reason == "model_abstained"
    assert len(llm.calls) == 2, "one answer attempt and one decomposition, never a third call"


def test_second_pass_can_be_switched_off():
    llm = FakeLLM([ABSTAIN])
    service = make_service(llm, second_pass_on_abstain=False)
    service.ingest("policy.txt", TWO_FACTS)

    assert service.ask(TWO_PART_QUESTION).response.answerable is False
    assert len(llm.calls) == 1


def test_position_aware_order_puts_the_strongest_at_the_edges():
    chunks = [_scored(name, score) for name, score in [("r3", 0.7), ("r1", 0.9), ("r5", 0.5), ("r2", 0.8), ("r4", 0.6)]]
    assert [c.chunk.chunk_id for c in position_aware_order(chunks)] == ["r1", "r3", "r5", "r4", "r2"]
